"""Modal adapter integration-friendly tests.

These tests focus on the adapter surface without invoking real Modal services.
We monkeypatch the `modal` module so the adapter logic can be exercised end-to-end:

* canonical app naming and context binding
* required secret validation
* graceful handling of import/lookup/remote failures
* envelope decoding and error codes
"""

from __future__ import annotations

import json
import sys
import types
from typing import Dict

import pytest
import yaml

from apps.core.adapters.modal_adapter import ModalAdapter


pytestmark = pytest.mark.integration


def _registry_snapshot(required_secrets: list[str] | None = None) -> Dict[str, Dict[str, Dict[str, Dict[str, str]]]]:
    """Build a minimal registry snapshot structure expected by the adapter."""

    return {
        "processors": {
            "test/proc@1": {
                "image": {"oci": "ghcr.io/example/test-proc@sha256:abc123"},
                "runtime": {"cpu": "1", "memory_gb": 2},
                "secrets": {"required": required_secrets or []},
            }
        }
    }


def _adapter_kwargs(**overrides):
    """Base kwargs for ModalAdapter.invoke with sensible defaults."""

    base = {
        "processor_ref": "test/proc@1",
        "mode": "mock",
        "inputs_json": {"schema": "v1", "params": {"ping": True}},
        "write_prefix": "/artifacts/outputs/test/{execution_id}/",
        "execution_id": "exec-123",
        "registry_snapshot": _registry_snapshot(),
        "adapter_opts": {"env_name": "dev"},
        "secrets_present": ["OPENAI_API_KEY"],
    }
    base.update(overrides)
    return base


class DummyFunction:
    """Dummy Modal.Function.lookup result."""

    def __init__(self, response_bytes: bytes, *, raise_on_remote: Exception | None = None):
        self._response = response_bytes
        self._raise = raise_on_remote
        self.received_payload = None

    def remote(self, payload):
        self.received_payload = payload
        if self._raise:
            raise self._raise
        return self._response


def _install_modal(monkeypatch, function_lookup):
    """Install a fake `modal` module with a configurable Function.lookup."""

    module = types.ModuleType("modal")
    module.Function = types.SimpleNamespace(lookup=function_lookup)
    monkeypatch.setitem(sys.modules, "modal", module)


class TestModalAdapter:
    def setup_method(self):
        self.adapter = ModalAdapter()

    def test_successful_invoke_returns_remote_envelope(self, monkeypatch):
        envelope = {
            "status": "success",
            "execution_id": "exec-123",
            "outputs": [{"path": "/artifacts/outputs/test/file.txt", "cid": "b3:123"}],
            "index_path": "/artifacts/outputs/test/index.json",
            "meta": {"env_fingerprint": "image:test"},
        }
        dummy_fn = DummyFunction(json.dumps(envelope).encode("utf-8"))

        def lookup(app_name, fn_name, environment_name):
            assert app_name == "test-proc-v1"
            assert fn_name == "run"
            assert environment_name == "dev"
            return dummy_fn

        _install_modal(monkeypatch, lookup)

        result = self.adapter.invoke(**_adapter_kwargs())

        assert result == envelope
        assert dummy_fn.received_payload["execution_id"] == "exec-123"

    def test_missing_required_secret_raises_error(self, monkeypatch):
        _install_modal(monkeypatch, lambda *a, **k: DummyFunction(b"{}"))

        kwargs = _adapter_kwargs(
            registry_snapshot=_registry_snapshot(required_secrets=["OPENAI_API_KEY", "SECONDARY_SECRET"]),
            secrets_present=["OPENAI_API_KEY"],
        )

        result = self.adapter.invoke(**kwargs)

        assert result["status"] == "error"
        assert result["error"]["code"] == "ERR_MISSING_SECRET"

    def test_modal_sdk_missing(self, monkeypatch):
        # Remove any cached modal module and make import raise ImportError
        sys.modules.pop("modal", None)

        import builtins

        real_import = builtins.__import__

        def raising_import(name, *args, **kwargs):
            if name == "modal":
                raise ImportError("modal not installed")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", raising_import)

        result = self.adapter.invoke(**_adapter_kwargs())

        assert result["status"] == "error"
        assert result["error"]["code"] == "ERR_DEPENDENCY"

    def test_modal_lookup_failure(self, monkeypatch):
        def failing_lookup(*_args, **_kwargs):
            raise RuntimeError("not found")

        _install_modal(monkeypatch, failing_lookup)

        result = self.adapter.invoke(**_adapter_kwargs())

        assert result["status"] == "error"
        assert result["error"]["code"] == "ERR_MODAL_LOOKUP"

    def test_modal_remote_failure(self, monkeypatch):
        dummy_fn = DummyFunction(b"", raise_on_remote=RuntimeError("boom"))

        def lookup(*_args, **_kwargs):
            return dummy_fn

        _install_modal(monkeypatch, lookup)

        result = self.adapter.invoke(**_adapter_kwargs())

        assert result["status"] == "error"
        assert result["error"]["code"] == "ERR_MODAL_INVOCATION"

    def test_modal_returns_invalid_json(self, monkeypatch):
        dummy_fn = DummyFunction(b"not-json")

        def lookup(*_args, **_kwargs):
            return dummy_fn

        _install_modal(monkeypatch, lookup)

        result = self.adapter.invoke(**_adapter_kwargs())

        assert result["status"] == "error"
        assert result["error"]["code"] == "ERR_MODAL_PAYLOAD"
