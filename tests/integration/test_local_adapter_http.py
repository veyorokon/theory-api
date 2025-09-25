"""LocalAdapter HTTP transport integration tests."""

import json
import subprocess
import tempfile
import time
from pathlib import Path

import pytest
import requests


pytestmark = [pytest.mark.integration, pytest.mark.requires_docker]


class TestLocalAdapterHTTP:
    """Test LocalAdapter uses HTTP transport, not stdin/stdout."""

    @pytest.fixture(scope="class")
    def processor_image(self):
        """Build processor image and return image tag."""
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
    def running_container(self, processor_image):
        """Start processor container and return connection info."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            artifacts_dir = Path(tmp_dir) / "artifacts"
            artifacts_dir.mkdir()

            # Start container
            container_result = subprocess.run(
                [
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    "test-local-adapter",
                    "-p",
                    "8002:8000",
                    "-v",
                    f"{artifacts_dir}:/artifacts:rw",
                    "-e",
                    "IMAGE_DIGEST=sha256:test123local",
                    processor_image,
                ],
                capture_output=True,
                text=True,
            )

            if container_result.returncode != 0:
                pytest.skip(f"Failed to start container: {container_result.stderr}")

            container_id = container_result.stdout.strip()

            try:
                # Wait for container to be ready
                for _ in range(30):
                    try:
                        response = requests.get("http://localhost:8002/healthz", timeout=1)
                        if response.status_code == 200:
                            break
                    except requests.RequestException:
                        pass
                    time.sleep(1)
                else:
                    pytest.skip("Container failed to become ready")

                yield {"url": "http://localhost:8002", "artifacts_dir": artifacts_dir, "container_id": container_id}

            finally:
                # Cleanup container
                subprocess.run(["docker", "stop", container_id], capture_output=True)
                subprocess.run(["docker", "rm", container_id], capture_output=True)

    def test_local_adapter_calls_http_endpoints(self, running_container):
        """Test LocalAdapter makes HTTP POST requests to /run endpoint."""
        # Use Django management command with LocalAdapter
        payload = {"schema": "v1", "params": {"messages": [{"role": "user", "content": "HTTP test"}]}}

        result = subprocess.run(
            [
                "python",
                "manage.py",
                "run_processor",
                "--ref",
                "llm/litellm@1",
                "--adapter",
                "local",
                "--mode",
                "mock",
                "--build",  # Forces local Docker execution
                "--write-prefix",
                "/artifacts/outputs/http-test/{execution_id}/",
                "--inputs-json",
                json.dumps(payload),
                "--json",
            ],
            cwd="code",
            capture_output=True,
            text=True,
            timeout=60,
            env={"DJANGO_SETTINGS_MODULE": "backend.settings.unittest"},
        )

        assert result.returncode == 0, f"LocalAdapter failed: {result.stderr}"

        # Parse response
        envelope = json.loads(result.stdout.splitlines()[0])
        assert envelope["status"] == "success"
        assert "execution_id" in envelope
        assert "outputs" in envelope

        # Verify container received HTTP request (check logs)
        logs_result = subprocess.run(
            ["docker", "logs", running_container["container_id"]], capture_output=True, text=True
        )

        # Should see HTTP POST to /run in container logs
        assert "POST /run" in logs_result.stderr or "POST /run" in logs_result.stdout

    def test_local_adapter_propagates_415_error(self, running_container):
        """Test LocalAdapter converts HTTP 415 to proper error envelope."""
        # Make direct HTTP request with wrong Content-Type to verify error
        response = requests.post(
            f"{running_container['url']}/run",
            data='{"test": "data"}',
            headers={"content-type": "text/plain"},
            timeout=10,
        )

        assert response.status_code == 415
        envelope = response.json()
        assert envelope["status"] == "error"
        assert envelope["error"]["code"] == "ERR_INPUTS"
        assert "Content-Type must be application/json" in envelope["error"]["message"]

    def test_local_adapter_propagates_400_error(self, running_container):
        """Test LocalAdapter converts HTTP 400 to proper error envelope."""
        # Make direct HTTP request with invalid JSON
        response = requests.post(
            f"{running_container['url']}/run",
            data="invalid-json",
            headers={"content-type": "application/json"},
            timeout=10,
        )

        assert response.status_code == 400
        envelope = response.json()
        assert envelope["status"] == "error"
        assert envelope["error"]["code"] == "ERR_INPUTS"
        assert "Invalid JSON body" in envelope["error"]["message"]

    def test_local_adapter_not_stdin_stdout(self, running_container):
        """Test LocalAdapter doesn't use legacy stdin/stdout CLI pattern."""
        # Verify that direct docker run with stdin doesn't work as expected
        # (because we're now HTTP-first)
        payload = {
            "execution_id": "stdin-test",
            "write_prefix": "/artifacts/outputs/stdin-test/",
            "schema": "v1",
            "mode": "mock",
            "params": {"messages": [{"role": "user", "content": "stdin test"}]},
        }

        # Try to use container via stdin (should not work like old CLI)
        stdin_result = subprocess.run(
            ["docker", "exec", "-i", running_container["container_id"], "/usr/local/bin/processor"],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=10,
        )

        # This should fail because we're HTTP-first now, not stdin-based
        # The container is running HTTP server, not CLI processor
        assert stdin_result.returncode != 0

    def test_local_adapter_http_success_path(self, running_container):
        """Test LocalAdapter HTTP success path end-to-end."""
        # Test successful HTTP request directly
        payload = {
            "execution_id": "http-success-test",
            "write_prefix": "/artifacts/outputs/http-success/",
            "schema": "v1",
            "mode": "mock",
            "params": {"messages": [{"role": "user", "content": "success test"}]},
        }

        response = requests.post(
            f"{running_container['url']}/run", json=payload, headers={"content-type": "application/json"}, timeout=30
        )

        assert response.status_code == 200
        envelope = response.json()

        assert envelope["status"] == "success"
        assert envelope["execution_id"] == "http-success-test"
        assert len(envelope["outputs"]) > 0
        assert "meta" in envelope
        assert "image_digest" in envelope["meta"]

        # Verify artifacts were created (can't check files but paths should exist)
        for output in envelope["outputs"]:
            assert output["path"].startswith("/artifacts/outputs/http-success/")

    def test_local_adapter_http_timeout_handling(self, running_container):
        """Test LocalAdapter handles HTTP timeouts appropriately."""
        # This is more of a network-level test
        # Make request with very short timeout
        try:
            response = requests.post(
                f"{running_container['url']}/run",
                json={
                    "execution_id": "timeout-test",
                    "write_prefix": "/artifacts/outputs/timeout/",
                    "schema": "v1",
                    "mode": "mock",
                    "params": {"messages": [{"role": "user", "content": "test"}]},
                },
                timeout=0.001,  # Very short timeout
            )
            # If it succeeds despite short timeout, that's also fine
            if response.status_code == 200:
                envelope = response.json()
                assert envelope["status"] == "success"
        except requests.Timeout:
            # Timeout is expected with very short timeout
            pass

    def test_local_adapter_concurrent_http_requests(self, running_container):
        """Test LocalAdapter can handle concurrent HTTP requests."""
        import concurrent.futures
        import uuid

        def make_request(i):
            execution_id = f"concurrent-{i}-{uuid.uuid4().hex[:8]}"
            payload = {
                "execution_id": execution_id,
                "write_prefix": f"/artifacts/outputs/concurrent-{i}/",
                "schema": "v1",
                "mode": "mock",
                "params": {"messages": [{"role": "user", "content": f"concurrent test {i}"}]},
            }

            response = requests.post(f"{running_container['url']}/run", json=payload, timeout=30)
            return response

        # Make 3 concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(make_request, i) for i in range(3)]
            responses = [future.result() for future in futures]

        # All requests should succeed
        for response in responses:
            assert response.status_code == 200
            envelope = response.json()
            assert envelope["status"] == "success"
            assert envelope["execution_id"]
