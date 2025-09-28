"""HTTP contract tests for processor FastAPI endpoints."""

import json
import pytest
from fastapi.testclient import TestClient


@pytest.mark.contracts
class TestHTTPContractBasic:
    """Test basic HTTP contract for processor endpoints."""

    @pytest.fixture
    def client(self):
        """FastAPI test client for llm/litellm processor."""
        # Import the HTTP app from the processor
        try:
            from apps.core.processors.llm_litellm.app.http import app

            return TestClient(app)
        except ImportError:
            pytest.skip("HTTP app not available for llm/litellm processor")

    @pytest.fixture
    def mock_image_digest(self, monkeypatch):
        """Ensure IMAGE_DIGEST is set for successful requests."""
        monkeypatch.setenv("IMAGE_DIGEST", "sha256:deadbeef")

    def test_healthz_endpoint(self, client):
        """Test /healthz returns 200 with ok=true."""
        response = client.get("/healthz")
        assert response.status_code == 200
        assert response.json() == {"ok": True}

    def test_run_endpoint_success(self, client, mock_image_digest):
        """Test /run returns success envelope for valid payload."""
        payload = {
            "execution_id": "test-123",
            "write_prefix": "/tmp/test/",
            "schema": "v1",
            "mode": "mock",
            "inputs": {"schema": "v1", "params": {"messages": [{"role": "user", "content": "test message"}]}},
        }

        response = client.post("/run", json=payload)
        assert response.status_code == 200

        envelope = response.json()
        assert envelope["status"] == "success"
        assert envelope["execution_id"] == "test-123"
        assert "outputs" in envelope
        assert "meta" in envelope
        assert "image_digest" in envelope["meta"]

    def test_run_endpoint_missing_execution_id(self, client):
        """Test /run returns error for missing execution_id."""
        payload = {
            "write_prefix": "/tmp/test/",
            "schema": "v1",
            "mode": "mock",
            "params": {"messages": [{"role": "user", "content": "test"}]},
        }

        response = client.post("/run", json=payload)
        assert response.status_code == 400

        envelope = response.json()
        assert envelope["status"] == "error"
        assert envelope["error"]["code"] == "ERR_INPUTS"
        assert "execution_id" in envelope["error"]["message"]

    def test_run_endpoint_invalid_json(self, client):
        """Test /run returns 400 for invalid JSON."""
        response = client.post("/run", data="invalid json", headers={"content-type": "application/json"})
        assert response.status_code == 400

        envelope = response.json()
        assert envelope["status"] == "error"
        assert envelope["error"]["code"] == "ERR_INPUTS"

    def test_run_endpoint_wrong_content_type(self, client):
        """Test /run returns 415 for wrong Content-Type."""
        payload = {"execution_id": "test"}
        response = client.post("/run", data=json.dumps(payload), headers={"content-type": "text/plain"})
        assert response.status_code == 415

        envelope = response.json()
        assert envelope["status"] == "error"
        assert envelope["error"]["code"] == "ERR_INPUTS"

    def test_run_endpoint_image_digest_validation(self, client):
        """Test /run validates IMAGE_DIGEST environment variable."""
        import os

        # Save original value
        original_digest = os.environ.get("IMAGE_DIGEST")

        try:
            # Remove IMAGE_DIGEST
            if "IMAGE_DIGEST" in os.environ:
                del os.environ["IMAGE_DIGEST"]

            payload = {
                "execution_id": "test-123",
                "write_prefix": "/tmp/test/",
                "schema": "v1",
                "mode": "mock",
                "params": {"messages": [{"role": "user", "content": "test"}]},
            }

            response = client.post("/run", json=payload)
            assert response.status_code == 500

            envelope = response.json()
            assert envelope["status"] == "error"
            assert envelope["error"]["code"] == "ERR_IMAGE_DIGEST_MISSING"

        finally:
            # Restore original value
            if original_digest:
                os.environ["IMAGE_DIGEST"] = original_digest
