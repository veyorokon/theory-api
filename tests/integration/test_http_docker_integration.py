"""HTTP Docker integration tests for processor containers."""

import json
import tempfile
import time
from pathlib import Path

import pytest
import requests
from testcontainers.compose import DockerCompose


pytestmark = [pytest.mark.integration, pytest.mark.requires_docker]


class TestHTTPDockerIntegration:
    """Test HTTP processors running in Docker containers."""

    @pytest.fixture(scope="class")
    def processor_container(self):
        """Start processor container and return its URL."""
        # Build processor image first
        import subprocess

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
        image_tag = build_info["image_tag"]

        # Start container with temp artifacts volume
        with tempfile.TemporaryDirectory() as tmp_dir:
            artifacts_dir = Path(tmp_dir) / "artifacts"
            artifacts_dir.mkdir()

            container_result = subprocess.run(
                [
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    "test-processor",
                    "-p",
                    "8000:8000",
                    "-v",
                    f"{artifacts_dir}:/artifacts:rw",
                    "-e",
                    "IMAGE_DIGEST=sha256:test123",
                    image_tag,
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
                        response = requests.get("http://localhost:8000/healthz", timeout=1)
                        if response.status_code == 200:
                            break
                    except requests.RequestException:
                        pass
                    time.sleep(1)
                else:
                    pytest.skip("Container failed to become ready")

                yield {"url": "http://localhost:8000", "artifacts_dir": artifacts_dir, "container_id": container_id}

            finally:
                # Cleanup container
                subprocess.run(["docker", "stop", container_id], capture_output=True)
                subprocess.run(["docker", "rm", container_id], capture_output=True)

    def test_healthz_endpoint(self, processor_container):
        """Test /healthz endpoint returns healthy status."""
        url = processor_container["url"]

        response = requests.get(f"{url}/healthz", timeout=5)
        assert response.status_code == 200
        assert response.json() == {"ok": True}

    def test_run_endpoint_creates_artifacts(self, processor_container):
        """Test /run endpoint creates proper artifacts structure."""
        url = processor_container["url"]
        artifacts_dir = processor_container["artifacts_dir"]
        execution_id = "test-integration-123"

        payload = {
            "execution_id": execution_id,
            "write_prefix": f"/artifacts/outputs/{execution_id}/",
            "schema": "v1",
            "mode": "mock",
            "params": {"messages": [{"role": "user", "content": "integration test"}]},
        }

        response = requests.post(f"{url}/run", json=payload, headers={"Content-Type": "application/json"}, timeout=30)

        assert response.status_code == 200
        envelope = response.json()

        # Validate envelope
        assert envelope["status"] == "success"
        assert envelope["execution_id"] == execution_id
        assert "outputs" in envelope
        assert "index_path" in envelope

        # Validate artifacts exist
        output_dir = artifacts_dir / "outputs" / execution_id
        assert output_dir.exists()

        # Check index file exists
        index_file = Path(envelope["index_path"])
        # Convert container path to host path
        host_index_path = artifacts_dir / index_file.relative_to("/artifacts")
        assert host_index_path.exists()

        # Validate index content
        with open(host_index_path) as f:
            index_data = json.load(f)
        assert "outputs" in index_data
        assert len(index_data["outputs"]) > 0

        # Check output files exist
        for output in envelope["outputs"]:
            output_path = Path(output["path"])
            host_output_path = artifacts_dir / output_path.relative_to("/artifacts")
            assert host_output_path.exists()
            assert host_output_path.stat().st_size > 0

    def test_run_endpoint_logging_to_stderr(self, processor_container):
        """Test that processor logs structured data to stderr."""
        container_id = processor_container["container_id"]

        payload = {
            "execution_id": "test-logging-456",
            "write_prefix": "/artifacts/outputs/test-logging-456/",
            "schema": "v1",
            "mode": "mock",
            "params": {"messages": [{"role": "user", "content": "log test"}]},
        }

        # Make request
        url = processor_container["url"]
        response = requests.post(f"{url}/run", json=payload, timeout=30)
        assert response.status_code == 200

        # Check container logs for structured NDJSON
        import subprocess

        logs_result = subprocess.run(["docker", "logs", container_id], capture_output=True, text=True)

        stderr_lines = logs_result.stderr.strip().split("\n")

        # Look for structured log entries
        structured_logs = []
        for line in stderr_lines:
            if line.strip():
                try:
                    log_entry = json.loads(line)
                    if "event" in log_entry or "level" in log_entry:
                        structured_logs.append(log_entry)
                except json.JSONDecodeError:
                    # Skip non-JSON lines (startup messages, etc.)
                    pass

        # Should have at least some structured log entries
        assert len(structured_logs) > 0

    def test_concurrent_requests(self, processor_container):
        """Test processor handles concurrent requests correctly."""
        import concurrent.futures
        import uuid

        url = processor_container["url"]

        def make_request(i):
            execution_id = f"concurrent-{i}-{uuid.uuid4().hex[:8]}"
            payload = {
                "execution_id": execution_id,
                "write_prefix": f"/artifacts/outputs/{execution_id}/",
                "schema": "v1",
                "mode": "mock",
                "params": {"messages": [{"role": "user", "content": f"concurrent test {i}"}]},
            }

            response = requests.post(f"{url}/run", json=payload, timeout=30)
            return response

        # Make 5 concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(make_request, i) for i in range(5)]
            responses = [future.result() for future in futures]

        # All requests should succeed
        for response in responses:
            assert response.status_code == 200
            envelope = response.json()
            assert envelope["status"] == "success"
            assert envelope["execution_id"]
