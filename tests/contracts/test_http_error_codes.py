"""HTTP error status codes contract tests for processor endpoints."""

import json
import pytest
from fastapi.testclient import TestClient


@pytest.mark.contracts
class TestHTTPErrorCodes:
    """Test HTTP error status codes return proper envelope format."""

    @pytest.fixture
    def client(self):
        """FastAPI test client for llm/litellm processor."""
        try:
            from apps.core.processors.llm_litellm.app.http import app

            return TestClient(app)
        except ImportError:
            pytest.skip("HTTP app not available for llm/litellm processor")

    def test_415_unsupported_media_type(self, client):
        """Test HTTP 415 returns proper ERR_INPUTS envelope."""
        response = client.post("/run", data='{"execution_id":"test"}', headers={"content-type": "text/plain"})

        assert response.status_code == 415
        envelope = response.json()
        assert envelope["status"] == "error"
        assert envelope["error"]["code"] == "ERR_INPUTS"
        assert "Content-Type must be application/json" in envelope["error"]["message"]
        assert envelope["execution_id"] == ""
        assert "meta" in envelope

    def test_400_invalid_json(self, client):
        """Test HTTP 400 for malformed JSON returns ERR_INPUTS."""
        response = client.post("/run", data="not-json", headers={"content-type": "application/json"})

        assert response.status_code == 400
        envelope = response.json()
        assert envelope["status"] == "error"
        assert envelope["error"]["code"] == "ERR_INPUTS"
        assert "Invalid JSON body" in envelope["error"]["message"]
        assert envelope["execution_id"] == ""

    def test_400_schema_validation_missing_execution_id(self, client):
        """Test HTTP 400 for missing execution_id returns ERR_INPUTS."""
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
        assert "missing execution_id" in envelope["error"]["message"]
        assert envelope["execution_id"] == ""

    def test_400_schema_validation_missing_write_prefix(self, client):
        """Test HTTP 400 for missing write_prefix returns ERR_INPUTS."""
        payload = {
            "execution_id": "test-123",
            "schema": "v1",
            "mode": "mock",
            "params": {"messages": [{"role": "user", "content": "test"}]},
        }

        response = client.post("/run", json=payload)

        assert response.status_code == 400
        envelope = response.json()
        assert envelope["status"] == "error"
        assert envelope["error"]["code"] == "ERR_INPUTS"
        assert "write_prefix" in envelope["error"]["message"].lower()

    def test_500_server_crash_envelope(self, client):
        """Test HTTP 500 returns proper ERR_RUNTIME envelope on server errors."""
        # Test with missing IMAGE_DIGEST env var to trigger server error
        import os

        original_digest = os.environ.get("IMAGE_DIGEST")

        try:
            # Remove IMAGE_DIGEST to trigger server error
            if "IMAGE_DIGEST" in os.environ:
                del os.environ["IMAGE_DIGEST"]

            payload = {
                "execution_id": "test-500",
                "write_prefix": "/tmp/test/",
                "schema": "v1",
                "mode": "mock",
                "params": {"messages": [{"role": "user", "content": "test"}]},
            }

            response = client.post("/run", json=payload)

            assert response.status_code == 500
            envelope = response.json()
            assert envelope["status"] == "error"
            assert envelope["execution_id"] == "test-500"
            assert envelope["error"]["code"] == "ERR_IMAGE_DIGEST_MISSING"
            assert "IMAGE_DIGEST env var not set" in envelope["error"]["message"]

        finally:
            # Restore original value
            if original_digest:
                os.environ["IMAGE_DIGEST"] = original_digest

    def test_error_envelope_consistency(self, client):
        """Test all error envelopes have consistent structure."""
        # Test multiple error conditions to verify envelope consistency
        error_cases = [
            # Wrong Content-Type
            {"method": "post_data", "data": '{"test":"data"}', "headers": {"content-type": "text/plain"}},
            # Invalid JSON
            {"method": "post_data", "data": "invalid-json", "headers": {"content-type": "application/json"}},
        ]

        for case in error_cases:
            if case["method"] == "post_data":
                response = client.post("/run", data=case["data"], headers=case["headers"])

            # All error responses must be JSON
            assert response.headers["content-type"] == "application/json"

            envelope = response.json()

            # All error envelopes must have consistent structure
            assert "status" in envelope
            assert envelope["status"] == "error"
            assert "execution_id" in envelope
            assert "error" in envelope
            assert "meta" in envelope

            # Error object must have required fields
            assert "code" in envelope["error"]
            assert "message" in envelope["error"]

            # Error code must start with ERR_
            assert envelope["error"]["code"].startswith("ERR_")

            # Message must be non-empty string
            assert isinstance(envelope["error"]["message"], str)
            assert len(envelope["error"]["message"]) > 0

    def test_non_json_response_rejected(self, client):
        """Test processor only accepts JSON requests."""
        # Test various non-JSON content types
        non_json_types = ["text/plain", "application/xml", "application/x-www-form-urlencoded", "multipart/form-data"]

        for content_type in non_json_types:
            response = client.post("/run", data='{"execution_id":"test"}', headers={"content-type": content_type})

            assert response.status_code == 415
            envelope = response.json()
            assert envelope["error"]["code"] == "ERR_INPUTS"
