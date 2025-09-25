"""Log structure contract tests for HTTP processors."""

import json
import subprocess
import tempfile
import time
from pathlib import Path

import pytest
import requests


pytestmark = [pytest.mark.unit]


class TestLogContract:
    """Test structured logging contract for HTTP processors."""

    @pytest.fixture(scope="class")
    def processor_image(self):
        """Build processor image for log testing."""
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
    def container_with_logs(self, processor_image):
        """Start container and return connection info for log testing."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            artifacts_dir = Path(tmp_dir) / "artifacts"
            artifacts_dir.mkdir()

            container_result = subprocess.run(
                [
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    "test-log-contract",
                    "-p",
                    "8004:8000",
                    "-v",
                    f"{artifacts_dir}:/artifacts:rw",
                    "-e",
                    "IMAGE_DIGEST=sha256:logtest123",
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
                        response = requests.get("http://localhost:8004/healthz", timeout=1)
                        if response.status_code == 200:
                            break
                    except requests.RequestException:
                        pass
                    time.sleep(1)
                else:
                    pytest.skip("Container failed to become ready")

                yield {"url": "http://localhost:8004", "container_id": container_id}

            finally:
                subprocess.run(["docker", "stop", container_id], capture_output=True)
                subprocess.run(["docker", "rm", container_id], capture_output=True)

    def _extract_json_logs(self, container_id):
        """Extract structured JSON logs from container stderr."""
        logs_result = subprocess.run(["docker", "logs", container_id], capture_output=True, text=True)

        # Parse NDJSON logs from stderr
        json_logs = []
        for line in logs_result.stderr.split("\n"):
            line = line.strip()
            if line and line.startswith("{"):
                try:
                    log_entry = json.loads(line)
                    json_logs.append(log_entry)
                except json.JSONDecodeError:
                    # Skip non-JSON lines (like uvicorn startup messages)
                    pass

        return json_logs

    def test_http_run_lifecycle_logs_success(self, container_with_logs):
        """Test handler emits http.run.start → handler.*.ok → http.run.settle for success."""
        payload = {
            "execution_id": "log-success-test",
            "write_prefix": "/artifacts/outputs/log-success/",
            "schema": "v1",
            "mode": "mock",
            "params": {"messages": [{"role": "user", "content": "log success test"}]},
        }

        # Clear any existing logs by getting current state
        _ = self._extract_json_logs(container_with_logs["container_id"])

        # Make request
        response = requests.post(f"{container_with_logs['url']}/run", json=payload, timeout=30)
        assert response.status_code == 200

        # Extract logs
        json_logs = self._extract_json_logs(container_with_logs["container_id"])

        # Filter logs for this execution
        execution_logs = [log for log in json_logs if log.get("execution_id") == "log-success-test"]

        assert len(execution_logs) >= 2, f"Expected at least start+settle logs, got: {execution_logs}"

        # Find key lifecycle events
        start_logs = [log for log in execution_logs if log.get("event") == "http.run.start"]
        settle_logs = [log for log in execution_logs if log.get("event") == "http.run.settle"]
        handler_logs = [log for log in execution_logs if "handler." in log.get("event", "")]

        # Must have start and settle
        assert len(start_logs) >= 1, f"Missing http.run.start log: {execution_logs}"
        assert len(settle_logs) >= 1, f"Missing http.run.settle log: {execution_logs}"

        # Should have handler-specific log
        assert len(handler_logs) >= 1, f"Missing handler log: {execution_logs}"

        # Verify log structure
        start_log = start_logs[0]
        assert start_log["level"] == "info"
        assert start_log["execution_id"] == "log-success-test"
        assert "ts" in start_log
        assert start_log["service"] == "processor"

        settle_log = settle_logs[0]
        assert settle_log["level"] == "info"
        assert settle_log["execution_id"] == "log-success-test"
        assert settle_log["status"] == "success"
        assert "elapsed_ms" in settle_log

    def test_http_run_error_logs(self, container_with_logs):
        """Test handler emits http.run.error for error cases."""
        # Test wrong Content-Type to trigger error
        response = requests.post(
            f"{container_with_logs['url']}/run",
            data='{"test": "data"}',
            headers={"content-type": "text/plain"},
            timeout=10,
        )
        assert response.status_code == 415

        # Extract logs
        json_logs = self._extract_json_logs(container_with_logs["container_id"])

        # Find error logs
        error_logs = [log for log in json_logs if log.get("event") == "http.run.error"]

        assert len(error_logs) >= 1, f"Missing http.run.error log: {json_logs}"

        error_log = error_logs[0]
        assert error_log["level"] == "info"
        assert error_log["reason"] == "unsupported_media_type"
        assert error_log["service"] == "processor"

    def test_log_structure_required_fields(self, container_with_logs):
        """Test all structured logs have required fields."""
        payload = {
            "execution_id": "log-fields-test",
            "write_prefix": "/artifacts/outputs/log-fields/",
            "schema": "v1",
            "mode": "mock",
            "params": {"messages": [{"role": "user", "content": "log fields test"}]},
        }

        # Make request
        response = requests.post(f"{container_with_logs['url']}/run", json=payload, timeout=30)
        assert response.status_code == 200

        # Extract logs
        json_logs = self._extract_json_logs(container_with_logs["container_id"])

        # Filter for execution logs
        execution_logs = [log for log in json_logs if log.get("execution_id") == "log-fields-test"]

        assert len(execution_logs) >= 1, "Should have execution logs"

        # Verify required fields in all execution logs
        required_fields = ["ts", "level", "event", "service"]

        for log_entry in execution_logs:
            for field in required_fields:
                assert field in log_entry, f"Log missing required field {field}: {log_entry}"

            # Verify field formats
            assert log_entry["level"] in ["info", "warn", "error", "debug"]
            assert log_entry["service"] == "processor"
            assert log_entry["event"]  # Non-empty string

            # Timestamp should be ISO format
            ts = log_entry["ts"]
            assert "T" in ts and "Z" in ts, f"Invalid timestamp format: {ts}"

    def test_log_redaction_patterns(self, container_with_logs):
        """Test logs don't contain sensitive information."""
        # This is more of a structural test since we're in mock mode
        payload = {
            "execution_id": "log-redaction-test",
            "write_prefix": "/artifacts/outputs/log-redaction/",
            "schema": "v1",
            "mode": "mock",
            "params": {
                "messages": [{"role": "user", "content": "test with potential secret sk-1234567890abcdef"}],
                "api_key": "sk-fake-key-for-testing",  # This should be filtered
            },
        }

        # Make request
        response = requests.post(f"{container_with_logs['url']}/run", json=payload, timeout=30)
        assert response.status_code == 200

        # Extract all logs
        json_logs = self._extract_json_logs(container_with_logs["container_id"])

        # Convert all logs to strings for pattern checking
        all_log_text = json.dumps(json_logs, separators=(",", ":"))

        # Should not contain API key patterns
        secret_patterns = [
            "sk-fake-key-for-testing",
            "sk-1234567890abcdef",
            "Bearer sk-",
        ]

        for pattern in secret_patterns:
            assert pattern not in all_log_text, f"Found secret pattern '{pattern}' in logs"

        # Should contain redaction markers if secrets were present
        # (This depends on actual redaction implementation)

    def test_log_json_format_valid(self, container_with_logs):
        """Test all logs are valid JSON (NDJSON format)."""
        payload = {
            "execution_id": "log-json-test",
            "write_prefix": "/artifacts/outputs/log-json/",
            "schema": "v1",
            "mode": "mock",
            "params": {"messages": [{"role": "user", "content": "json format test"}]},
        }

        # Make request
        response = requests.post(f"{container_with_logs['url']}/run", json=payload, timeout=30)
        assert response.status_code == 200

        # Get raw stderr
        logs_result = subprocess.run(
            ["docker", "logs", container_with_logs["container_id"]], capture_output=True, text=True
        )

        stderr_lines = logs_result.stderr.strip().split("\n")

        # Filter for JSON-like lines
        json_lines = [line.strip() for line in stderr_lines if line.strip().startswith("{")]

        assert len(json_lines) > 0, "Should have JSON log lines"

        # Each line should be valid JSON
        for line in json_lines:
            try:
                json.loads(line)
            except json.JSONDecodeError as e:
                pytest.fail(f"Invalid JSON in log line: {line} - Error: {e}")

    def test_log_levels_appropriate(self, container_with_logs):
        """Test logs use appropriate levels for different events."""
        # Test success case
        success_payload = {
            "execution_id": "log-level-success",
            "write_prefix": "/artifacts/outputs/log-level-success/",
            "schema": "v1",
            "mode": "mock",
            "params": {"messages": [{"role": "user", "content": "success test"}]},
        }

        response = requests.post(f"{container_with_logs['url']}/run", json=success_payload, timeout=30)
        assert response.status_code == 200

        # Test error case
        error_response = requests.post(
            f"{container_with_logs['url']}/run",
            data="invalid-json",
            headers={"content-type": "application/json"},
            timeout=10,
        )
        assert error_response.status_code == 400

        # Extract logs
        json_logs = self._extract_json_logs(container_with_logs["container_id"])

        # Success logs should be 'info' level
        success_logs = [log for log in json_logs if log.get("execution_id") == "log-level-success"]
        for log_entry in success_logs:
            assert log_entry["level"] == "info", f"Success logs should be info level: {log_entry}"

        # Error logs should be 'info' level (structured error events, not crashes)
        error_logs = [log for log in json_logs if log.get("event") == "http.run.error"]
        for log_entry in error_logs:
            assert log_entry["level"] == "info", f"Error event logs should be info level: {log_entry}"

    def test_log_timing_information(self, container_with_logs):
        """Test logs include appropriate timing information."""
        payload = {
            "execution_id": "log-timing-test",
            "write_prefix": "/artifacts/outputs/log-timing/",
            "schema": "v1",
            "mode": "mock",
            "params": {"messages": [{"role": "user", "content": "timing test"}]},
        }

        # Make request
        response = requests.post(f"{container_with_logs['url']}/run", json=payload, timeout=30)
        assert response.status_code == 200

        # Extract logs
        json_logs = self._extract_json_logs(container_with_logs["container_id"])

        # Find settle log with timing
        settle_logs = [
            log
            for log in json_logs
            if log.get("event") == "http.run.settle" and log.get("execution_id") == "log-timing-test"
        ]

        assert len(settle_logs) >= 1, "Should have settle log with timing"

        settle_log = settle_logs[0]
        assert "elapsed_ms" in settle_log, f"Settle log missing elapsed_ms: {settle_log}"
        assert isinstance(settle_log["elapsed_ms"], (int, float)), "elapsed_ms should be numeric"
        assert settle_log["elapsed_ms"] >= 0, "elapsed_ms should be non-negative"
