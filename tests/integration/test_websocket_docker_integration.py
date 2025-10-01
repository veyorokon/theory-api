"""WebSocket Docker integration tests for processor containers."""

import json
import os
import subprocess
import tempfile
import time
import asyncio
from pathlib import Path

import pytest
import requests
import websockets
from websockets.exceptions import ConnectionClosedError

from tests.tools.subprocess_helper import run_manage_py


pytestmark = [pytest.mark.integration, pytest.mark.requires_docker]


class TestWebSocketDockerIntegration:
    """Test WebSocket processors running in Docker containers."""

    @pytest.fixture(scope="class")
    def processor_container(self):
        """Start processor container and return its WebSocket URL."""
        # Build processor image first
        result = run_manage_py(
            "build_processor",
            "--ref",
            "llm/litellm@1",
            "--json",
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
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
                    "test-ws-processor",
                    "-p",
                    "8000:8000",
                    "-v",
                    f"{artifacts_dir}:/artifacts:rw",
                    "--user",
                    f"{os.getuid()}:{os.getgid()}",
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
                # Wait for container to be ready (health check)
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

                yield {
                    "ws_url": "ws://localhost:8000",
                    "http_url": "http://localhost:8000",
                    "artifacts_dir": artifacts_dir,
                    "container_id": container_id,
                }

            finally:
                # Cleanup container
                subprocess.run(["docker", "stop", container_id], capture_output=True)
                subprocess.run(["docker", "rm", container_id], capture_output=True)

    def test_healthz_endpoint_still_http(self, processor_container):
        """Test /healthz endpoint remains HTTP."""
        http_url = processor_container["http_url"]

        response = requests.get(f"{http_url}/healthz", timeout=5)
        assert response.status_code == 200
        assert response.json() == {"ok": True}

    @pytest.mark.asyncio
    async def test_websocket_connection_establishes(self, processor_container):
        """Test WebSocket connection establishes with theory.run.v1 subprotocol."""
        ws_url = processor_container["ws_url"]
        uri = f"{ws_url}/run"

        try:
            async with websockets.connect(uri, subprotocols=["theory.run.v1"]) as websocket:
                assert websocket.subprotocol == "theory.run.v1"
                assert websocket.state.name == "OPEN"
        except Exception as e:
            pytest.fail(f"WebSocket connection failed: {e}")

    @pytest.mark.asyncio
    async def test_websocket_run_creates_artifacts(self, processor_container):
        """Test WebSocket /run creates proper artifacts structure."""
        ws_url = processor_container["ws_url"]
        artifacts_dir = processor_container["artifacts_dir"]
        execution_id = "test-ws-integration-123"

        payload = {
            "kind": "RunOpen",
            "content": {
                "role": "client",
                "execution_id": execution_id,
                "payload": {
                    "execution_id": execution_id,
                    "write_prefix": f"/artifacts/outputs/{execution_id}/",
                    "schema": "v1",
                    "mode": "mock",
                    "inputs": {
                        "schema": "v1",
                        "params": {"messages": [{"role": "user", "content": "WebSocket integration test"}]},
                    },
                },
            },
        }

        uri = f"{ws_url}/run"

        try:
            async with websockets.connect(uri, subprotocols=["theory.run.v1"]) as websocket:
                await websocket.send(json.dumps(payload))

                # Collect messages until RunResult
                envelope = None
                max_messages = 50
                message_count = 0

                while envelope is None and message_count < max_messages:
                    try:
                        message = await asyncio.wait_for(websocket.recv(), timeout=30.0)
                        data = json.loads(message)

                        if data.get("kind") == "RunResult":
                            envelope = data["content"]
                            break

                        message_count += 1
                    except TimeoutError:
                        pytest.fail("Timeout waiting for RunResult")

                assert envelope is not None, "Expected RunResult frame not received"

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

        except Exception as e:
            pytest.fail(f"WebSocket integration test failed: {e}")

    @pytest.mark.asyncio
    async def test_websocket_streaming_events(self, processor_container):
        """Test WebSocket streams events during processing."""
        ws_url = processor_container["ws_url"]
        execution_id = "test-ws-streaming-456"

        payload = {
            "kind": "RunOpen",
            "content": {
                "role": "client",
                "execution_id": execution_id,
                "payload": {
                    "execution_id": execution_id,
                    "write_prefix": f"/artifacts/outputs/{execution_id}/",
                    "schema": "v1",
                    "mode": "mock",
                    "inputs": {
                        "schema": "v1",
                        "params": {"messages": [{"role": "user", "content": "streaming events test"}]},
                    },
                },
            },
        }

        uri = f"{ws_url}/run"

        try:
            async with websockets.connect(uri, subprotocols=["theory.run.v1"]) as websocket:
                await websocket.send(json.dumps(payload))

                messages = []
                max_messages = 100
                start_time = asyncio.get_event_loop().time()

                while len(messages) < max_messages:
                    try:
                        # Calculate remaining timeout
                        elapsed = asyncio.get_event_loop().time() - start_time
                        remaining_timeout = max(0.1, 30.0 - elapsed)

                        message = await asyncio.wait_for(websocket.recv(), timeout=remaining_timeout)
                        data = json.loads(message)
                        messages.append(data)

                        # Stop when we get RunResult
                        if data.get("kind") == "RunResult":
                            break

                    except TimeoutError:
                        break
                    except ConnectionClosedError:
                        break

                assert len(messages) > 0, "Should receive at least one message"

                # Last message should be RunResult
                final_message = messages[-1]
                assert final_message.get("kind") == "RunResult"

                # Check for valid event types
                valid_event_kinds = {"Token", "Frame", "Log", "Event", "RunResult"}
                for message in messages:
                    assert message.get("kind") in valid_event_kinds

                # Final envelope should be success
                envelope = final_message["content"]
                assert envelope["status"] == "success"
                assert envelope["execution_id"] == execution_id

        except Exception as e:
            pytest.fail(f"WebSocket streaming test failed: {e}")

    def test_container_logging_to_stderr(self, processor_container):
        """Test that processor logs structured data to stderr."""
        container_id = processor_container["container_id"]
        ws_url = processor_container["ws_url"]

        # Make a simple WebSocket request to generate logs
        async def make_ws_request():
            payload = {
                "kind": "RunOpen",
                "content": {
                    "role": "client",
                    "execution_id": "test-logging-789",
                    "payload": {
                        "execution_id": "test-logging-789",
                        "write_prefix": "/artifacts/outputs/test-logging-789/",
                        "schema": "v1",
                        "mode": "mock",
                        "inputs": {"schema": "v1", "params": {"messages": [{"role": "user", "content": "log test"}]}},
                    },
                },
            }

            uri = f"{ws_url}/run"
            async with websockets.connect(uri, subprotocols=["theory.run.v1"]) as websocket:
                await websocket.send(json.dumps(payload))

                # Wait for RunResult
                while True:
                    message = await asyncio.wait_for(websocket.recv(), timeout=30.0)
                    data = json.loads(message)
                    if data.get("kind") == "RunResult":
                        return data["content"]

        # Run the WebSocket request
        try:
            envelope = asyncio.run(make_ws_request())
            assert envelope["status"] == "success"
        except Exception as e:
            pytest.fail(f"WebSocket logging test request failed: {e}")

        # Check container logs for structured NDJSON
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

    @pytest.mark.asyncio
    async def test_concurrent_websocket_connections(self, processor_container):
        """Test processor handles concurrent WebSocket connections correctly."""
        ws_url = processor_container["ws_url"]

        async def make_ws_request(i):
            execution_id = f"concurrent-ws-{i}"
            payload = {
                "kind": "RunOpen",
                "content": {
                    "role": "client",
                    "execution_id": execution_id,
                    "payload": {
                        "execution_id": execution_id,
                        "write_prefix": f"/artifacts/outputs/{execution_id}/",
                        "schema": "v1",
                        "mode": "mock",
                        "inputs": {
                            "schema": "v1",
                            "params": {"messages": [{"role": "user", "content": f"concurrent test {i}"}]},
                        },
                    },
                },
            }

            uri = f"{ws_url}/run"
            async with websockets.connect(uri, subprotocols=["theory.run.v1"]) as websocket:
                await websocket.send(json.dumps(payload))

                # Wait for RunResult
                while True:
                    message = await asyncio.wait_for(websocket.recv(), timeout=30.0)
                    data = json.loads(message)
                    if data.get("kind") == "RunResult":
                        envelope = data["content"]
                        return envelope["status"], envelope["execution_id"]

        try:
            # Make 5 concurrent WebSocket requests
            tasks = [make_ws_request(i) for i in range(5)]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # All requests should succeed
            for result in results:
                if isinstance(result, Exception):
                    pytest.fail(f"Concurrent WebSocket test failed: {result}")
                else:
                    status, execution_id = result
                    assert status == "success"
                    assert execution_id.startswith("concurrent-ws-")

        except Exception as e:
            pytest.fail(f"WebSocket concurrent test failed: {e}")

    @pytest.mark.asyncio
    async def test_websocket_error_handling(self, processor_container):
        """Test WebSocket error handling in container."""
        ws_url = processor_container["ws_url"]

        # Send invalid payload to trigger error
        invalid_payload = {
            "kind": "RunOpen",
            "content": {
                "role": "client",
                "execution_id": "test-ws-error-abc",
                "payload": {
                    # Missing execution_id field
                    "write_prefix": "/artifacts/outputs/test-ws-error/",
                    "schema": "v1",
                    "mode": "mock",
                    "inputs": {"invalid": "structure"},
                },
            },
        }

        uri = f"{ws_url}/run"

        try:
            async with websockets.connect(uri, subprotocols=["theory.run.v1"]) as websocket:
                await websocket.send(json.dumps(invalid_payload))

                # Should get error response
                message = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                data = json.loads(message)

                assert data.get("kind") == "RunResult"
                envelope = data["content"]
                assert envelope["status"] == "error"
                assert "error" in envelope
                assert envelope["error"]["code"].startswith("ERR_")

        except Exception as e:
            pytest.fail(f"WebSocket error handling test failed: {e}")

    @pytest.mark.asyncio
    async def test_websocket_connection_timeout_handling(self, processor_container):
        """Test WebSocket connection handles timeouts gracefully."""
        ws_url = processor_container["ws_url"]
        uri = f"{ws_url}/run"

        try:
            async with websockets.connect(uri, subprotocols=["theory.run.v1"]) as websocket:
                # Don't send anything, just wait
                try:
                    # Test client timeout behavior
                    await asyncio.wait_for(websocket.recv(), timeout=1.0)
                except TimeoutError:
                    # Expected - no message sent
                    pass

                # Connection should still be open for normal operation
                assert websocket.state.name == "OPEN"

        except Exception as e:
            pytest.fail(f"WebSocket timeout test failed: {e}")

    @pytest.mark.asyncio
    async def test_websocket_vs_cli_consistency(self, processor_container):
        """Test WebSocket container produces same results as CLI orchestrator."""
        ws_url = processor_container["ws_url"]
        execution_id_ws = "consistency-ws-test"
        execution_id_cli = "consistency-cli-test"

        # Common inputs
        inputs = {"schema": "v1", "params": {"messages": [{"role": "user", "content": "consistency test"}]}}

        # Get result via direct WebSocket connection
        ws_payload = {
            "kind": "RunOpen",
            "content": {
                "role": "client",
                "execution_id": execution_id_ws,
                "payload": {
                    "execution_id": execution_id_ws,
                    "write_prefix": f"/artifacts/outputs/{execution_id_ws}/",
                    "schema": "v1",
                    "mode": "mock",
                    "inputs": inputs,
                },
            },
        }

        uri = f"{ws_url}/run"
        ws_envelope = None

        try:
            async with websockets.connect(uri, subprotocols=["theory.run.v1"]) as websocket:
                await websocket.send(json.dumps(ws_payload))

                # Wait for RunResult
                while True:
                    message = await asyncio.wait_for(websocket.recv(), timeout=30.0)
                    data = json.loads(message)
                    if data.get("kind") == "RunResult":
                        ws_envelope = data["content"]
                        break

        except Exception as e:
            pytest.fail(f"Direct WebSocket test failed: {e}")

        # Get result via CLI orchestrator (which also uses WebSocket under the hood)
        with tempfile.TemporaryDirectory() as tmp_dir:
            write_prefix = f"{tmp_dir}/outputs/{execution_id_cli}/"

            result = run_manage_py(
                "run_processor",
                "--ref",
                "llm/litellm@1",
                "--adapter",
                "local",
                "--build",
                "--mode",
                "mock",
                "--write-prefix",
                write_prefix,
                "--inputs-json",
                json.dumps(inputs),
                "--json",
                capture_output=True,
                text=True,
                timeout=120,
            )

            assert result.returncode == 0, f"CLI command failed: {result.stderr}"
            cli_envelope = json.loads(result.stdout)

        # Compare envelopes (ignoring execution_id and paths)
        assert ws_envelope["status"] == cli_envelope["status"] == "success"
        assert len(ws_envelope["outputs"]) == len(cli_envelope["outputs"])
        assert "meta" in ws_envelope and "meta" in cli_envelope
        assert "image_digest" in ws_envelope["meta"] and "image_digest" in cli_envelope["meta"]
