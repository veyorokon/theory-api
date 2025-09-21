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


class FakeInvoker:
    """Fake ModalInvoker for testing."""

    def __init__(self, response_bytes: bytes, *, raise_on_invoke: Exception | None = None):
        self._response = response_bytes
        self._raise = raise_on_invoke
        self.received_payload = None
        self.received_fn_fullname = None
        self.was_called = False

    def invoke(self, fn_fullname: str, payload: dict, timeout_s: int) -> bytes:
        self.was_called = True
        self.received_fn_fullname = fn_fullname
        self.received_payload = payload
        if self._raise:
            raise self._raise
        return self._response


def _install_modal(monkeypatch, from_name_fn):
    """Install mock modal module with given from_name function."""
    mock_modal = types.ModuleType("modal")
    mock_modal.Function = types.SimpleNamespace()
    mock_modal.Function.from_name = from_name_fn
    monkeypatch.setitem(sys.modules, "modal", mock_modal)


class DummyFunction:
    """Dummy Modal function for testing."""

    def __init__(self, response_bytes: bytes, *, raise_on_remote: Exception | None = None):
        self._response = response_bytes
        self._raise = raise_on_remote

    def remote(self, payload):
        if self._raise:
            raise self._raise
        return self._response


class TestModalAdapter:
    @property
    def adapter(self):
        return ModalAdapter()

    def test_successful_invoke_returns_remote_envelope(self):
        envelope = {
            "status": "success",
            "execution_id": "exec-123",
            "outputs": [{"path": "/artifacts/outputs/test/file.txt", "cid": "b3:123"}],
            "index_path": "/artifacts/outputs/test/index.json",
            "meta": {"env_fingerprint": "image:test"},
        }
        fake_invoker = FakeInvoker(json.dumps(envelope).encode("utf-8"))
        adapter = ModalAdapter(invoker=fake_invoker)

        result = adapter.invoke(**_adapter_kwargs())

        assert result == envelope
        assert fake_invoker.received_fn_fullname == "test-proc-v1.run"
        assert fake_invoker.received_payload["execution_id"] == "exec-123"

    def test_missing_required_secret_raises_error(self):
        fake_invoker = FakeInvoker(b"{}")
        adapter = ModalAdapter(invoker=fake_invoker)

        kwargs = _adapter_kwargs(
            mode="real",  # Must be real mode to trigger secret validation
            registry_snapshot=_registry_snapshot(required_secrets=["OPENAI_API_KEY", "SECONDARY_SECRET"]),
            secrets_present=["OPENAI_API_KEY"],  # Missing SECONDARY_SECRET
        )

        result = adapter.invoke(**kwargs)

        assert result["status"] == "error"
        assert result["error"]["code"] == "ERR_MISSING_SECRET"
        assert fake_invoker.was_called is False  # Should fail before invoker call

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

        result = ModalAdapter().invoke(**_adapter_kwargs())

        assert result["status"] == "error"
        assert result["error"]["code"] == "ERR_MODAL_INVOCATION"

    def test_modal_lookup_failure(self, monkeypatch):
        def failing_from_name(*_args, **_kwargs):
            raise RuntimeError("not found")

        _install_modal(monkeypatch, failing_from_name)

        result = ModalAdapter().invoke(**_adapter_kwargs())

        assert result["status"] == "error"
        assert result["error"]["code"] == "ERR_MODAL_LOOKUP"

    def test_modal_remote_failure(self, monkeypatch):
        dummy_fn = DummyFunction(b"", raise_on_remote=RuntimeError("boom"))

        def from_name(*_args, **_kwargs):
            return dummy_fn

        _install_modal(monkeypatch, from_name)

        result = ModalAdapter().invoke(**_adapter_kwargs())

        assert result["status"] == "error"
        assert result["error"]["code"] == "ERR_MODAL_INVOCATION"

    def test_modal_returns_invalid_json(self, monkeypatch):
        dummy_fn = DummyFunction(b"not-json")

        def from_name(*_args, **_kwargs):
            return dummy_fn

        _install_modal(monkeypatch, from_name)

        result = ModalAdapter().invoke(**_adapter_kwargs())

        assert result["status"] == "error"
        assert result["error"]["code"] == "ERR_MODAL_PAYLOAD"
