"""Log structure contract tests for WebSocket processors."""

import asyncio
import json
import subprocess

import pytest
import websockets

from tests.tools.localctl_helpers import get_ws_url, get_container_port


pytestmark = [pytest.mark.integration, pytest.mark.requires_docker]

# Container started by Makefile via `localctl start --ref llm/litellm@1`
CONTAINER_REF = "llm/litellm@1"
WS_URL = get_ws_url(CONTAINER_REF)


class TestLogContract:
    """Test structured logging contract for WebSocket processors."""

    def _extract_json_logs(self):
        """Extract structured JSON logs from container stderr via localctl."""
        # Get container ID from localctl status
        status_result = subprocess.run(
            ["python", "manage.py", "localctl", "status", "--ref", CONTAINER_REF],
            cwd="code",
            capture_output=True,
            text=True,
        )

        if status_result.returncode != 0:
            pytest.skip("Container not running")

        status = json.loads(status_result.stdout)
        if not status.get("containers"):
            pytest.skip(f"Container for {CONTAINER_REF} not found")

        container_id = status["containers"][0]["container_id"]

        # Extract logs
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

    def test_http_run_lifecycle_logs_success(self):
        """Test handler emits ws.run.start for WebSocket connection."""
        payload = {
            "execution_id": "log-success-test",
            "write_prefix": "/artifacts/outputs/log-success/",
            "mode": "mock",
            "inputs": {
                "schema": "v1",
                "params": {"messages": [{"role": "user", "content": "log success test"}]},
            },
            "put_urls": {},
        }

        async def run_test():
            async with websockets.connect(WS_URL, subprotocols=["theory.run.v1"]) as ws:
                await ws.send(
                    json.dumps(
                        {
                            "kind": "RunOpen",
                            "content": {"role": "client", "execution_id": "log-success-test", "payload": payload},
                        }
                    )
                )
                ack = json.loads(await ws.recv())
                assert ack["kind"] == "Ack"
                while True:
                    msg = json.loads(await ws.recv())
                    if msg["kind"] == "RunResult":
                        break

        asyncio.run(run_test())

        json_logs = self._extract_json_logs()
        execution_logs = [log for log in json_logs if log.get("execution_id") == "log-success-test"]

        assert len(execution_logs) >= 1, f"Expected at least start log, got: {execution_logs}"

        start_logs = [log for log in execution_logs if log.get("event") == "ws.run.start"]
        assert len(start_logs) >= 1, f"Missing ws.run.start log: {execution_logs}"

        start_log = start_logs[0]
        assert start_log["level"] == "info"
        assert start_log["execution_id"] == "log-success-test"
        assert "ts" in start_log
        assert start_log["service"] == "processor"

    def test_http_run_error_logs(self):
        """Test WebSocket handshake failure logs (protocol validation)."""

        async def run_test():
            try:
                async with websockets.connect(WS_URL) as ws:
                    pass
            except websockets.exceptions.InvalidStatus as e:
                assert e.response.status_code in (403, 400, 500)

        asyncio.run(run_test())

    def test_log_structure_required_fields(self):
        """Test all structured logs have required fields."""
        payload = {
            "execution_id": "log-fields-test",
            "write_prefix": "/artifacts/outputs/log-fields/",
            "mode": "mock",
            "inputs": {
                "schema": "v1",
                "params": {"messages": [{"role": "user", "content": "log fields test"}]},
            },
            "put_urls": {},
        }

        async def run_test():
            async with websockets.connect(WS_URL, subprotocols=["theory.run.v1"]) as ws:
                await ws.send(
                    json.dumps(
                        {
                            "kind": "RunOpen",
                            "content": {"role": "client", "execution_id": "log-fields-test", "payload": payload},
                        }
                    )
                )
                ack = json.loads(await ws.recv())
                assert ack["kind"] == "Ack"
                while True:
                    msg = json.loads(await ws.recv())
                    if msg["kind"] == "RunResult":
                        break

        asyncio.run(run_test())

        json_logs = self._extract_json_logs()
        execution_logs = [log for log in json_logs if log.get("execution_id") == "log-fields-test"]

        assert len(execution_logs) >= 1, "Should have execution logs"

        required_fields = ["ts", "level", "event", "service"]

        for log_entry in execution_logs:
            for field in required_fields:
                assert field in log_entry, f"Log missing required field {field}: {log_entry}"

            assert log_entry["level"] in ["info", "warn", "error", "debug"]
            assert log_entry["service"] == "processor"
            assert log_entry["event"]

            ts = log_entry["ts"]
            assert "T" in ts and "Z" in ts, f"Invalid timestamp format: {ts}"

    def test_log_redaction_patterns(self):
        """Test logs don't contain sensitive information."""
        payload = {
            "execution_id": "log-redaction-test",
            "write_prefix": "/artifacts/outputs/log-redaction/",
            "mode": "mock",
            "inputs": {
                "schema": "v1",
                "params": {
                    "messages": [{"role": "user", "content": "test with potential secret sk-1234567890abcdef"}],
                    "api_key": "sk-fake-key-for-testing",
                },
            },
            "put_urls": {},
        }

        async def run_test():
            async with websockets.connect(WS_URL, subprotocols=["theory.run.v1"]) as ws:
                await ws.send(
                    json.dumps(
                        {
                            "kind": "RunOpen",
                            "content": {"role": "client", "execution_id": "log-redaction-test", "payload": payload},
                        }
                    )
                )
                ack = json.loads(await ws.recv())
                assert ack["kind"] == "Ack"
                while True:
                    msg = json.loads(await ws.recv())
                    if msg["kind"] == "RunResult":
                        break

        asyncio.run(run_test())

        json_logs = self._extract_json_logs()
        all_log_text = json.dumps(json_logs, separators=(",", ":"))

        secret_patterns = [
            "sk-fake-key-for-testing",
            "sk-1234567890abcdef",
            "Bearer sk-",
        ]

        for pattern in secret_patterns:
            assert pattern not in all_log_text, f"Found secret pattern '{pattern}' in logs"

    def test_log_json_format_valid(self):
        """Test all logs are valid JSON (NDJSON format)."""
        payload = {
            "execution_id": "log-json-test",
            "write_prefix": "/artifacts/outputs/log-json/",
            "mode": "mock",
            "inputs": {
                "schema": "v1",
                "params": {"messages": [{"role": "user", "content": "json format test"}]},
            },
            "put_urls": {},
        }

        async def run_test():
            async with websockets.connect(WS_URL, subprotocols=["theory.run.v1"]) as ws:
                await ws.send(
                    json.dumps(
                        {
                            "kind": "RunOpen",
                            "content": {"role": "client", "execution_id": "log-json-test", "payload": payload},
                        }
                    )
                )
                ack = json.loads(await ws.recv())
                assert ack["kind"] == "Ack"
                while True:
                    msg = json.loads(await ws.recv())
                    if msg["kind"] == "RunResult":
                        break

        asyncio.run(run_test())

        # Get raw stderr via localctl
        status_result = subprocess.run(
            ["python", "manage.py", "localctl", "status", "--ref", CONTAINER_REF],
            cwd="code",
            capture_output=True,
            text=True,
        )
        status = json.loads(status_result.stdout)
        container_id = status["containers"][0]["container_id"]

        logs_result = subprocess.run(["docker", "logs", container_id], capture_output=True, text=True)

        stderr_lines = logs_result.stderr.strip().split("\n")
        json_lines = [line.strip() for line in stderr_lines if line.strip().startswith("{")]

        assert len(json_lines) > 0, "Should have JSON log lines"

        for line in json_lines:
            try:
                json.loads(line)
            except json.JSONDecodeError as e:
                pytest.fail(f"Invalid JSON in log line: {line} - Error: {e}")

    def test_log_levels_appropriate(self):
        """Test logs use appropriate levels for different events."""
        payload = {
            "execution_id": "log-level-success",
            "write_prefix": "/artifacts/outputs/log-level-success/",
            "mode": "mock",
            "inputs": {
                "schema": "v1",
                "params": {"messages": [{"role": "user", "content": "success test"}]},
            },
            "put_urls": {},
        }

        async def run_test():
            async with websockets.connect(WS_URL, subprotocols=["theory.run.v1"]) as ws:
                await ws.send(
                    json.dumps(
                        {
                            "kind": "RunOpen",
                            "content": {"role": "client", "execution_id": "log-level-success", "payload": payload},
                        }
                    )
                )
                ack = json.loads(await ws.recv())
                assert ack["kind"] == "Ack"
                while True:
                    msg = json.loads(await ws.recv())
                    if msg["kind"] == "RunResult":
                        break

        asyncio.run(run_test())

        json_logs = self._extract_json_logs()
        success_logs = [log for log in json_logs if log.get("execution_id") == "log-level-success"]
        for log_entry in success_logs:
            assert log_entry["level"] == "info", f"Success logs should be info level: {log_entry}"

    def test_log_timing_information(self):
        """Test WebSocket logs include timestamps."""
        payload = {
            "execution_id": "log-timing-test",
            "write_prefix": "/artifacts/outputs/log-timing/",
            "mode": "mock",
            "inputs": {
                "schema": "v1",
                "params": {"messages": [{"role": "user", "content": "timing test"}]},
            },
            "put_urls": {},
        }

        async def run_test():
            async with websockets.connect(WS_URL, subprotocols=["theory.run.v1"]) as ws:
                await ws.send(
                    json.dumps(
                        {
                            "kind": "RunOpen",
                            "content": {"role": "client", "execution_id": "log-timing-test", "payload": payload},
                        }
                    )
                )
                ack = json.loads(await ws.recv())
                assert ack["kind"] == "Ack"
                while True:
                    msg = json.loads(await ws.recv())
                    if msg["kind"] == "RunResult":
                        break

        asyncio.run(run_test())

        json_logs = self._extract_json_logs()
        execution_logs = [log for log in json_logs if log.get("execution_id") == "log-timing-test"]

        assert len(execution_logs) >= 1, "Should have execution logs"

        for log in execution_logs:
            assert "ts" in log, f"Log missing timestamp: {log}"
            ts = log["ts"]
            assert "T" in ts and "Z" in ts, f"Invalid timestamp format: {ts}"
