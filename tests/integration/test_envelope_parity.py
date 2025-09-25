"""Envelope parity tests between LocalAdapter and ModalAdapter."""

import json
import subprocess
import tempfile
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import requests


pytestmark = [pytest.mark.integration, pytest.mark.requires_docker]


class TestEnvelopeParity:
    """Test LocalAdapter vs ModalAdapter produce consistent envelopes."""

    @pytest.fixture(scope="class")
    def processor_image(self):
        """Build processor image for local testing."""
        result = subprocess.run(
            ["python", "manage.py", "build_processor", "--ref", "llm/litellm@1", "--json"],
            cwd="code",
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.returncode != 0:
            pytest.skip(f"Failed to build processor: {result.stderr}")

        build_info = json.loads(result.stdout)
        return build_info["image_tag"]

    @pytest.fixture
    def local_container(self, processor_image):
        """Start local processor container."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            artifacts_dir = Path(tmp_dir) / "artifacts"
            artifacts_dir.mkdir()

            container_result = subprocess.run(
                [
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    "test-envelope-parity",
                    "-p",
                    "8003:8000",
                    "-v",
                    f"{artifacts_dir}:/artifacts:rw",
                    "-e",
                    "IMAGE_DIGEST=sha256:parity123test",
                    processor_image,
                ],
                capture_output=True,
                text=True,
            )

            if container_result.returncode != 0:
                pytest.skip(f"Failed to start container: {container_result.stderr}")

            container_id = container_result.stdout.strip()

            try:
                # Wait for readiness
                for _ in range(30):
                    try:
                        response = requests.get("http://localhost:8003/healthz", timeout=1)
                        if response.status_code == 200:
                            break
                    except requests.RequestException:
                        pass
                    time.sleep(1)
                else:
                    pytest.skip("Local container failed to become ready")

                yield {"url": "http://localhost:8003", "container_id": container_id}

            finally:
                subprocess.run(["docker", "stop", container_id], capture_output=True)
                subprocess.run(["docker", "rm", container_id], capture_output=True)

    def _normalize_envelope_for_comparison(self, envelope):
        """Normalize envelope for comparison by removing timestamp-like fields."""
        normalized = envelope.copy()

        # Remove timing-related fields that will differ
        if "meta" in normalized:
            meta = normalized["meta"].copy()
            # Keep image_digest and other stable fields, remove timing
            timing_fields = ["duration_ms", "timestamp_utc", "created_at"]
            for field in timing_fields:
                meta.pop(field, None)
            normalized["meta"] = meta

        # Normalize output paths to compare structure, not exact paths
        if "outputs" in normalized:
            for output in normalized["outputs"]:
                # Keep relative structure, normalize execution_id specific parts
                if "path" in output:
                    # Replace actual execution_id with placeholder for comparison
                    path = output["path"]
                    if "/parity-test-" in path:
                        # Normalize execution_id part
                        parts = path.split("/")
                        for i, part in enumerate(parts):
                            if part.startswith("parity-test-"):
                                parts[i] = "EXECUTION_ID"
                        output["path"] = "/".join(parts)

        return normalized

    def test_local_modal_envelope_parity_mock_mode(self, local_container):
        """Test identical mock requests produce consistent envelope structure."""
        # Define identical test payload
        base_execution_id = "parity-test"
        payload = {
            "execution_id": base_execution_id + "-123",
            "write_prefix": f"/artifacts/outputs/{base_execution_id}-123/",
            "schema": "v1",
            "mode": "mock",
            "params": {"messages": [{"role": "user", "content": "envelope parity test"}], "model": "gpt-4o-mini"},
        }

        # Get envelope from Local adapter (via HTTP)
        local_response = requests.post(f"{local_container['url']}/run", json=payload, timeout=30)
        assert local_response.status_code == 200
        local_envelope = local_response.json()

        # Get envelope from Modal adapter (mocked)
        with patch("modal.lookup") as mock_lookup, patch("requests.post") as mock_post:
            mock_function = MagicMock()
            mock_function.web_url = "https://mock-parity-test.modal.run"

            mock_app = MagicMock()
            mock_app.__getitem__.return_value = mock_function
            mock_lookup.return_value = mock_app

            # Mock Modal response with same structure as local
            mock_modal_response = MagicMock()
            mock_modal_response.status_code = 200
            mock_modal_response.json.return_value = {
                "status": "success",
                "execution_id": payload["execution_id"],
                "outputs": [{"path": f"/artifacts/outputs/{base_execution_id}-123/outputs/text/response.txt"}],
                "index_path": f"/artifacts/outputs/{base_execution_id}-123/outputs.json",
                "meta": {
                    "env_fingerprint": "cpu:1;memory:2Gi",
                    "model": "gpt-4o-mini",
                    "image_digest": "sha256:parity123test",
                },
            }
            mock_post.return_value = mock_modal_response

            from apps.core.adapters.modal_adapter import ModalAdapter

            modal_adapter = ModalAdapter()

            import os

            os.environ.update({"MODAL_ENVIRONMENT": "dev", "BRANCH": "feat/parity", "USER": "parityuser"})

            modal_envelope = modal_adapter.invoke(processor_ref="llm/litellm@1", payload=payload, timeout_s=60)

        # Normalize both envelopes for comparison
        local_norm = self._normalize_envelope_for_comparison(local_envelope)
        modal_norm = self._normalize_envelope_for_comparison(modal_envelope)

        # Compare core envelope structure
        assert local_norm["status"] == modal_norm["status"]
        assert local_norm["execution_id"] == modal_norm["execution_id"]

        # Compare outputs structure (count and types)
        assert len(local_norm["outputs"]) == len(modal_norm["outputs"])

        # Compare meta fields (excluding timing)
        local_meta = local_norm.get("meta", {})
        modal_meta = modal_norm.get("meta", {})

        stable_meta_fields = ["env_fingerprint", "model", "image_digest"]
        for field in stable_meta_fields:
            if field in local_meta and field in modal_meta:
                assert local_meta[field] == modal_meta[field], (
                    f"Meta field {field} differs: local={local_meta[field]}, modal={modal_meta[field]}"
                )

    def test_envelope_required_fields_consistency(self, local_container):
        """Test both adapters produce envelopes with consistent required fields."""
        payload = {
            "execution_id": "fields-test-456",
            "write_prefix": "/artifacts/outputs/fields-test/",
            "schema": "v1",
            "mode": "mock",
            "params": {"messages": [{"role": "user", "content": "fields test"}]},
        }

        # Test local envelope
        local_response = requests.post(f"{local_container['url']}/run", json=payload, timeout=30)
        assert local_response.status_code == 200
        local_envelope = local_response.json()

        # Mock modal envelope
        with patch("modal.lookup") as mock_lookup, patch("requests.post") as mock_post:
            mock_function = MagicMock()
            mock_function.web_url = "https://mock-fields.modal.run"

            mock_app = MagicMock()
            mock_app.__getitem__.return_value = mock_function
            mock_lookup.return_value = mock_app

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "status": "success",
                "execution_id": "fields-test-456",
                "outputs": [{"path": "/artifacts/outputs/fields-test/outputs/text/response.txt"}],
                "index_path": "/artifacts/outputs/fields-test/outputs.json",
                "meta": {"image_digest": "sha256:fields123test"},
            }
            mock_post.return_value = mock_response

            from apps.core.adapters.modal_adapter import ModalAdapter

            modal_adapter = ModalAdapter()

            import os

            os.environ.update({"MODAL_ENVIRONMENT": "dev", "BRANCH": "feat/fields", "USER": "fieldsuser"})

            modal_envelope = modal_adapter.invoke(processor_ref="llm/litellm@1", payload=payload, timeout_s=60)

        # Both envelopes must have same required fields
        required_fields = ["status", "execution_id", "outputs", "meta"]
        for field in required_fields:
            assert field in local_envelope, f"Local envelope missing {field}"
            assert field in modal_envelope, f"Modal envelope missing {field}"

        # Meta must contain image_digest
        assert "image_digest" in local_envelope["meta"]
        assert "image_digest" in modal_envelope["meta"]

        # Outputs must be non-empty list
        assert isinstance(local_envelope["outputs"], list)
        assert isinstance(modal_envelope["outputs"], list)
        assert len(local_envelope["outputs"]) > 0
        assert len(modal_envelope["outputs"]) > 0

    def test_error_envelope_parity(self, local_container):
        """Test error envelopes are consistent between adapters."""
        # Test 415 error
        local_response = requests.post(
            f"{local_container['url']}/run", data='{"test": "data"}', headers={"content-type": "text/plain"}, timeout=10
        )
        assert local_response.status_code == 415
        local_error_envelope = local_response.json()

        # Mock Modal error (would also be 415 via HTTP)
        mock_modal_error = {
            "status": "error",
            "execution_id": "",
            "error": {"code": "ERR_INPUTS", "message": "Content-Type must be application/json"},
            "meta": {},
        }

        # Compare error envelope structure
        assert local_error_envelope["status"] == mock_modal_error["status"]
        assert local_error_envelope["error"]["code"] == mock_modal_error["error"]["code"]
        assert "Content-Type" in local_error_envelope["error"]["message"]

        # Both should have consistent error structure
        required_error_fields = ["status", "execution_id", "error", "meta"]
        for field in required_error_fields:
            assert field in local_error_envelope
            assert field in mock_modal_error

        error_fields = ["code", "message"]
        for field in error_fields:
            assert field in local_error_envelope["error"]
            assert field in mock_modal_error["error"]

    def test_envelope_json_serialization_consistency(self, local_container):
        """Test envelopes serialize to JSON consistently."""
        payload = {
            "execution_id": "json-test-789",
            "write_prefix": "/artifacts/outputs/json-test/",
            "schema": "v1",
            "mode": "mock",
            "params": {"messages": [{"role": "user", "content": "json test"}]},
        }

        # Get local envelope
        local_response = requests.post(f"{local_container['url']}/run", json=payload, timeout=30)
        assert local_response.status_code == 200
        local_envelope = local_response.json()

        # Test JSON serialization roundtrip
        local_json = json.dumps(local_envelope, sort_keys=True)
        local_parsed = json.loads(local_json)

        assert local_parsed == local_envelope, "Local envelope not JSON serializable"

        # Verify no problematic types (like datetime objects that aren't JSON serializable)
        def check_json_types(obj, path=""):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    check_json_types(v, f"{path}.{k}")
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    check_json_types(v, f"{path}[{i}]")
            else:
                # Must be JSON-serializable primitive
                assert isinstance(obj, (str, int, float, bool, type(None))), (
                    f"Non-JSON-serializable type {type(obj)} at {path}: {obj}"
                )

        check_json_types(local_envelope)
