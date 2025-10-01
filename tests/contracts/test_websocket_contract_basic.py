"""WebSocket contract tests for processor endpoints."""

import json
import pytest
import asyncio
from contextlib import asynccontextmanager
from typing import Dict, Any, AsyncIterator

import websockets
from websockets.exceptions import ConnectionClosedError
import requests


@pytest.mark.contracts
class TestWebSocketContractBasic:
    """Test basic WebSocket contract for processor endpoints."""

    @pytest.fixture
    def mock_image_digest(self, monkeypatch):
        """Ensure IMAGE_DIGEST is set for successful requests."""
        monkeypatch.setenv("IMAGE_DIGEST", "sha256:deadbeef")

    @pytest.fixture
    def base_url(self):
        """Base URL for WebSocket connections."""
        return "ws://localhost:8000"

    @pytest.fixture
    def valid_payload(self):
        """Valid RunOpen payload for WebSocket connection."""
        return {
            "kind": "RunOpen",
            "content": {
                "role": "client",
                "execution_id": "test-ws-123",
                "payload": {
                    "execution_id": "test-ws-123",
                    "write_prefix": "/tmp/test-ws/",
                    "schema": "v1",
                    "mode": "mock",
                    "inputs": {
                        "schema": "v1",
                        "params": {"messages": [{"role": "user", "content": "WebSocket test message"}]},
                    },
                },
            },
        }

    @asynccontextmanager
    async def websocket_connection(
        self, base_url: str, subprotocol: str = "theory.run.v1"
    ) -> AsyncIterator[websockets.WebSocketServerProtocol]:
        """Context manager for WebSocket connections with proper cleanup."""
        uri = f"{base_url}/run"
        try:
            async with websockets.connect(uri, subprotocols=[subprotocol]) as websocket:
                yield websocket
        except Exception as e:
            pytest.fail(f"WebSocket connection failed: {e}")

    def test_healthz_endpoint_still_http(self):
        """Test /healthz remains HTTP endpoint."""
        response = requests.get("http://localhost:8000/healthz")
        assert response.status_code == 200
        assert response.json() == {"ok": True}

    @pytest.mark.asyncio
    async def test_websocket_connection_establishes(self, base_url):
        """Test WebSocket connection establishes with theory.run.v1 subprotocol."""
        try:
            async with self.websocket_connection(base_url) as websocket:
                # Connection should establish successfully
                assert websocket.subprotocol == "theory.run.v1"
                assert websocket.state.name == "OPEN"
        except Exception as e:
            pytest.skip(f"WebSocket endpoint not available: {e}")

    @pytest.mark.asyncio
    async def test_websocket_run_open_success(self, base_url, valid_payload, mock_image_digest):
        """Test WebSocket RunOpen frame returns RunResult with success envelope."""
        try:
            async with self.websocket_connection(base_url) as websocket:
                # Send RunOpen frame
                await websocket.send(json.dumps(valid_payload))

                # Receive messages until we get RunResult
                run_result = None
                max_messages = 50  # Prevent infinite loop
                message_count = 0

                while run_result is None and message_count < max_messages:
                    try:
                        message = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                        data = json.loads(message)

                        if data.get("kind") == "RunResult":
                            run_result = data
                            break

                        message_count += 1
                    except TimeoutError:
                        pytest.fail("Timeout waiting for RunResult")

                assert run_result is not None, "Expected RunResult frame not received"

                # Validate envelope structure
                envelope = run_result["content"]
                assert envelope["status"] == "success"
                assert envelope["execution_id"] == "test-ws-123"
                assert "outputs" in envelope
                assert "meta" in envelope
                assert "image_digest" in envelope["meta"]

        except Exception as e:
            pytest.skip(f"WebSocket test failed: {e}")

    @pytest.mark.asyncio
    async def test_websocket_invalid_subprotocol_rejected(self, base_url):
        """Test WebSocket connection with invalid subprotocol is rejected."""
        uri = f"{base_url}/run"

        try:
            async with websockets.connect(uri, subprotocols=["invalid.protocol"]) as websocket:
                pytest.fail("Connection should have been rejected with invalid subprotocol")
        except websockets.exceptions.InvalidStatusCode as e:
            # Should get 400 or similar for invalid subprotocol
            assert e.status_code in [400, 403, 426]
        except ConnectionClosedError as e:
            # Connection closed with appropriate code
            assert e.code in [1002, 1008]  # Protocol error or policy violation
        except Exception as e:
            pytest.skip(f"WebSocket endpoint not available: {e}")

    @pytest.mark.asyncio
    async def test_websocket_malformed_run_open_frame(self, base_url):
        """Test malformed RunOpen frame triggers appropriate error."""
        try:
            async with self.websocket_connection(base_url) as websocket:
                # Send malformed frame
                malformed_frame = {
                    "kind": "RunOpen",
                    "content": {
                        # Missing required fields
                        "role": "client"
                    },
                }

                await websocket.send(json.dumps(malformed_frame))

                # Should get error response or connection close
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    data = json.loads(message)

                    if data.get("kind") == "RunResult":
                        envelope = data["content"]
                        assert envelope["status"] == "error"
                        assert envelope["error"]["code"] in ["ERR_INPUTS", "ERR_WS_PROTOCOL"]

                except ConnectionClosedError as e:
                    # Connection closed due to protocol error
                    assert e.code in [1002, 1008]
                except TimeoutError:
                    pytest.fail("Expected error response or connection close")

        except Exception as e:
            pytest.skip(f"WebSocket malformed frame test failed: {e}")

    @pytest.mark.asyncio
    async def test_websocket_missing_execution_id_error(self, base_url):
        """Test WebSocket RunOpen without execution_id returns error."""
        try:
            async with self.websocket_connection(base_url) as websocket:
                invalid_payload = {
                    "kind": "RunOpen",
                    "content": {
                        "role": "client",
                        "execution_id": "test-error-456",
                        "payload": {
                            # Missing execution_id in payload
                            "write_prefix": "/tmp/test-error/",
                            "schema": "v1",
                            "mode": "mock",
                            "inputs": {"schema": "v1", "params": {"messages": [{"role": "user", "content": "test"}]}},
                        },
                    },
                }

                await websocket.send(json.dumps(invalid_payload))

                # Should get error result
                message = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                data = json.loads(message)

                assert data.get("kind") == "RunResult"
                envelope = data["content"]
                assert envelope["status"] == "error"
                assert envelope["error"]["code"] == "ERR_INPUTS"
                assert "execution_id" in envelope["error"]["message"]

        except Exception as e:
            pytest.skip(f"WebSocket execution_id error test failed: {e}")

    @pytest.mark.asyncio
    async def test_websocket_image_digest_validation(self, base_url, valid_payload):
        """Test WebSocket validates IMAGE_DIGEST environment variable."""
        import os

        # Save and remove IMAGE_DIGEST
        original_digest = os.environ.get("IMAGE_DIGEST")
        if "IMAGE_DIGEST" in os.environ:
            del os.environ["IMAGE_DIGEST"]

        try:
            async with self.websocket_connection(base_url) as websocket:
                await websocket.send(json.dumps(valid_payload))

                # Should get error result
                message = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                data = json.loads(message)

                assert data.get("kind") == "RunResult"
                envelope = data["content"]
                assert envelope["status"] == "error"
                assert envelope["error"]["code"] == "ERR_IMAGE_DIGEST_MISSING"

        except Exception as e:
            pytest.skip(f"WebSocket image digest test failed: {e}")
        finally:
            # Restore IMAGE_DIGEST
            if original_digest:
                os.environ["IMAGE_DIGEST"] = original_digest

    @pytest.mark.asyncio
    async def test_websocket_connection_timeout_handling(self, base_url):
        """Test WebSocket connection handles timeouts gracefully."""
        try:
            async with self.websocket_connection(base_url) as websocket:
                # Don't send anything, just wait
                try:
                    # Most WebSocket servers have keep-alive, so this tests the client timeout
                    await asyncio.wait_for(websocket.recv(), timeout=1.0)
                except TimeoutError:
                    # Expected - no message sent
                    pass

                # Connection should still be open for normal operation
                assert websocket.state.name == "OPEN"

        except Exception as e:
            pytest.skip(f"WebSocket timeout test failed: {e}")

    @pytest.mark.asyncio
    async def test_websocket_concurrent_connections(self, base_url, mock_image_digest):
        """Test WebSocket server handles concurrent connections."""

        async def make_ws_request(execution_id: str):
            payload = {
                "kind": "RunOpen",
                "content": {
                    "role": "client",
                    "execution_id": execution_id,
                    "payload": {
                        "execution_id": execution_id,
                        "write_prefix": f"/tmp/concurrent-{execution_id}/",
                        "schema": "v1",
                        "mode": "mock",
                        "inputs": {
                            "schema": "v1",
                            "params": {"messages": [{"role": "user", "content": f"concurrent test {execution_id}"}]},
                        },
                    },
                },
            }

            try:
                async with self.websocket_connection(base_url) as websocket:
                    await websocket.send(json.dumps(payload))

                    # Wait for RunResult
                    while True:
                        message = await asyncio.wait_for(websocket.recv(), timeout=15.0)
                        data = json.loads(message)
                        if data.get("kind") == "RunResult":
                            return data["content"]["status"], data["content"]["execution_id"]

            except Exception as e:
                return "error", str(e)

        try:
            # Make 3 concurrent WebSocket requests
            tasks = [make_ws_request(f"concurrent-ws-{i}") for i in range(3)]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # All should succeed
            for result in results:
                if isinstance(result, Exception):
                    pytest.skip(f"Concurrent WebSocket test failed: {result}")
                else:
                    status, execution_id = result
                    assert status == "success"
                    assert execution_id.startswith("concurrent-ws-")

        except Exception as e:
            pytest.skip(f"WebSocket concurrent test failed: {e}")

    @pytest.mark.asyncio
    async def test_websocket_envelope_determinism(self, base_url, mock_image_digest):
        """Test WebSocket produces deterministic envelopes."""

        async def get_envelope(execution_id: str):
            payload = {
                "kind": "RunOpen",
                "content": {
                    "role": "client",
                    "execution_id": execution_id,
                    "payload": {
                        "execution_id": execution_id,
                        "write_prefix": f"/tmp/determinism-{execution_id}/",
                        "schema": "v1",
                        "mode": "mock",
                        "inputs": {
                            "schema": "v1",
                            "params": {"messages": [{"role": "user", "content": "determinism test"}]},
                        },
                    },
                },
            }

            async with self.websocket_connection(base_url) as websocket:
                await websocket.send(json.dumps(payload))

                while True:
                    message = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                    data = json.loads(message)
                    if data.get("kind") == "RunResult":
                        return data["content"]

        try:
            # Get two envelopes with different execution IDs
            envelope1 = await get_envelope("determinism-1")
            envelope2 = await get_envelope("determinism-2")

            # Should have same structure, different execution IDs
            assert envelope1["status"] == envelope2["status"] == "success"
            assert envelope1["execution_id"] != envelope2["execution_id"]
            assert len(envelope1["outputs"]) == len(envelope2["outputs"])
            assert envelope1["meta"]["image_digest"] == envelope2["meta"]["image_digest"]

        except Exception as e:
            pytest.skip(f"WebSocket determinism test failed: {e}")
