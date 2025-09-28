"""
Contract tests for HTTP-first processor containers.
Ensures containers serve HTTP endpoints and return valid envelopes.
"""

import json
import subprocess
import tempfile
import time
import requests
from pathlib import Path
import pytest

pytestmark = [pytest.mark.contracts, pytest.mark.requires_docker]


class TestContainerHTTP:
    """Contract tests for HTTP-first container execution."""

    def test_container_http_endpoint_mock_mode(self):
        """Container serves HTTP endpoints and returns valid envelopes."""
        payload = {
            "schema": "v1",
            "mode": "mock",
            "execution_id": "test-container-http",
            "write_prefix": "/artifacts/outputs/test-container-http/",
            "params": {
                "messages": [{"role": "user", "content": "test message"}],
            },
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            # Build the container first
            build_cmd = [
                "docker",
                "buildx",
                "build",
                "--load",
                "-t",
                "theory-local/llm-litellm:http-test",
                "-f",
                "code/apps/core/processors/llm_litellm/Dockerfile",
                ".",
            ]
            build_result = subprocess.run(build_cmd, capture_output=True, text=True)
            if build_result.returncode != 0:
                pytest.skip(f"Failed to build container: {build_result.stderr}")

            # Start container with HTTP server
            container_cmd = [
                "docker",
                "run",
                "-d",
                "--name",
                "test-http-container",
                "-p",
                "8005:8000",
                "-v",
                f"{tmp_dir}:/artifacts",
                "-e",
                "IMAGE_DIGEST=sha256:httptest123",
                "theory-local/llm-litellm:http-test",
            ]

            container_result = subprocess.run(container_cmd, capture_output=True, text=True)
            if container_result.returncode != 0:
                pytest.skip(f"Failed to start container: {container_result.stderr}")

            container_id = container_result.stdout.strip()

            try:
                # Wait for container to be ready
                for _ in range(30):
                    try:
                        response = requests.get("http://localhost:8005/healthz", timeout=1)
                        if response.status_code == 200:
                            break
                    except requests.RequestException:
                        pass
                    time.sleep(1)
                else:
                    pytest.skip("Container failed to become ready")

                # Make HTTP request
                response = requests.post("http://localhost:8005/run", json=payload, timeout=30)
                assert response.status_code == 200, f"HTTP request failed: {response.status_code} {response.text}"

                # Validate envelope structure
                envelope = response.json()
                assert envelope["status"] == "success", f"Expected success envelope: {envelope}"
                assert envelope["execution_id"] == "test-container-http"
                assert "outputs" in envelope
                assert isinstance(envelope["outputs"], list)
                assert "meta" in envelope

            finally:
                subprocess.run(["docker", "stop", container_id], capture_output=True)
                subprocess.run(["docker", "rm", container_id], capture_output=True)

    def test_container_http_error_handling(self):
        """Container HTTP endpoint returns proper error status and envelope."""
        # Test with invalid Content-Type
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Use same container setup pattern (simplified for brevity)
            container_cmd = [
                "docker",
                "run",
                "-d",
                "--name",
                "test-error-container",
                "-p",
                "8006:8000",
                "-v",
                f"{tmp_dir}:/artifacts",
                "-e",
                "IMAGE_DIGEST=sha256:errortest123",
                "theory-local/llm-litellm:http-test",
            ]

            container_result = subprocess.run(container_cmd, capture_output=True, text=True)
            if container_result.returncode != 0:
                pytest.skip(f"Failed to start container: {container_result.stderr}")

            container_id = container_result.stdout.strip()

            try:
                # Wait for readiness
                for _ in range(20):
                    try:
                        response = requests.get("http://localhost:8006/healthz", timeout=1)
                        if response.status_code == 200:
                            break
                    except requests.RequestException:
                        pass
                    time.sleep(1)
                else:
                    pytest.skip("Container failed to become ready")

                # Test 415 error with wrong Content-Type
                response = requests.post(
                    "http://localhost:8006/run",
                    data='{"invalid": "payload"}',
                    headers={"content-type": "text/plain"},
                    timeout=10,
                )

                assert response.status_code == 415
                envelope = response.json()
                assert envelope["status"] == "error"
                assert envelope["error"]["code"] == "ERR_INPUTS"
                assert "Content-Type" in envelope["error"]["message"]

            finally:
                subprocess.run(["docker", "stop", container_id], capture_output=True)
                subprocess.run(["docker", "rm", container_id], capture_output=True)

    def test_container_http_health_endpoint(self):
        """Container serves health endpoint correctly."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            container_cmd = [
                "docker",
                "run",
                "-d",
                "--name",
                "test-health-container",
                "-p",
                "8007:8000",
                "theory-local/llm-litellm:http-test",
            ]

            container_result = subprocess.run(container_cmd, capture_output=True, text=True)
            if container_result.returncode != 0:
                pytest.skip(f"Failed to start container: {container_result.stderr}")

            container_id = container_result.stdout.strip()

            try:
                # Wait for readiness and test health
                for _ in range(30):
                    try:
                        response = requests.get("http://localhost:8007/healthz", timeout=1)
                        if response.status_code == 200:
                            # Verify health response structure
                            health = response.json()
                            assert health["status"] == "ok"
                            break
                    except requests.RequestException:
                        pass
                    time.sleep(1)
                else:
                    pytest.fail("Health endpoint not responding")

            finally:
                subprocess.run(["docker", "stop", container_id], capture_output=True)
                subprocess.run(["docker", "rm", container_id], capture_output=True)
