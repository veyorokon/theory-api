"""Integration tests for Modal adapter public behavior: canonical output format,
duplicate detection, and disabled gating. Avoids internal method coupling.
"""

import json
import tarfile
import pytest
from io import BytesIO
from unittest.mock import patch

from django.test import override_settings

from apps.core.adapters.modal_adapter import ModalAdapter


pytestmark = pytest.mark.integration


def make_tar_bytes(files: dict[str, bytes]) -> bytes:
    buf = BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in files.items():
            ti = tarfile.TarInfo(name=name)
            ti.size = len(data)
            tar.addfile(ti, BytesIO(data))
    return buf.getvalue()


class TestModalAdapterParity:
    @override_settings(MODAL_ENABLED=True, MODAL_ENVIRONMENT="dev")
    @patch("apps.core.adapters.modal_adapter.storage_service")
    def test_success_envelope_from_tar(self, mock_storage_service):
        # Prepare tar with outputs
        tar_bytes = make_tar_bytes({"text/response.txt": b"OK", "meta.json": b"{}"})

        adapter = ModalAdapter()

        # Patch network call to Modal to return our tar
        with patch.object(adapter, "_call_generated", return_value=tar_bytes):
            # Minimal spec snapshot (no required secrets)
            snapshot = {
                "processors": {
                    "test/processor@1": {
                        "image": {"oci": "ghcr.io/example@sha256:abcdef0123456789"},
                        "runtime": {"cpu": 1, "memory_gb": 2, "timeout_s": 60},
                        "secrets": {"required": []},
                    }
                }
            }
            result = adapter.invoke(
                processor_ref="test/processor@1",
                inputs_json={"x": 1},
                write_prefix="/artifacts/outputs/",
                execution_id="exec-1",
                registry_snapshot=snapshot,
                adapter_opts={},
                secrets_present=[],
            )

        assert result["status"] == "success"
        assert result["execution_id"] == "exec-1"
        assert result["index_path"] == "/artifacts/execution/exec-1/outputs.json"
        assert isinstance(result["outputs"], list) and len(result["outputs"]) == 2
        assert "env_fingerprint" in result["meta"]

        # Ensure index write happened
        calls = [c for c in mock_storage_service.write_file.call_args_list if c[0][0].endswith("outputs.json")]
        assert calls, "outputs.json not written"
        payload = calls[0][0][1]
        idx = json.loads(payload)
        assert idx.get("outputs") and isinstance(idx["outputs"], list)

    @override_settings(MODAL_ENABLED=True, MODAL_ENVIRONMENT="dev")
    @patch("apps.core.adapters.modal_adapter.storage_service")
    def test_duplicate_detection(self, _mock_storage_service):
        # Use paths that canonicalize to the same target after normalization
        tar_bytes = make_tar_bytes({"dup.txt": b"a", "./dup.txt": b"b"})
        adapter = ModalAdapter()
        with patch.object(adapter, "_call_generated", return_value=tar_bytes):
            snapshot = {
                "processors": {
                    "test/processor@1": {
                        "image": {"oci": "ghcr.io/example@sha256:abcdef0123456789"},
                        "runtime": {},
                        "secrets": {"required": []},
                    }
                }
            }
            res = adapter.invoke(
                processor_ref="test/processor@1",
                inputs_json={},
                write_prefix="/artifacts/outputs/",
                execution_id="e",
                registry_snapshot=snapshot,
                adapter_opts={},
                secrets_present=[],
            )
        assert res["status"] == "error"
        # Canonicalization should fail with adapter invocation error for dot-segments
        assert res["error"]["code"] == "ERR_ADAPTER_INVOCATION"

    def test_disabled_gate(self):
        # When MODAL_ENABLED is False, adapter returns disabled error envelope
        with override_settings(MODAL_ENABLED=False):
            adapter = ModalAdapter()
            res = adapter.invoke(
                processor_ref="test/processor@1",
                inputs_json={},
                write_prefix="/artifacts/outputs/",
                execution_id="e",
                registry_snapshot={
                    "processors": {
                        "test/processor@1": {
                            "image": {"oci": "ghcr.io/x@sha256:1"},
                            "runtime": {},
                            "secrets": {"required": []},
                        }
                    }
                },
                adapter_opts={},
                secrets_present=[],
            )
            assert res["status"] == "error"
            assert res["error"]["code"] == "ERR_ADAPTER_INVOCATION"
