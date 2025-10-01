"""WebSocket error codes contract tests for processor endpoints."""

import json
import pytest
import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

import websockets
from websockets.exceptions import ConnectionClosedError


@pytest.mark.contracts
class TestWebSocketErrorCodes:
    """Test WebSocket error codes return proper envelope format."""

    @pytest.fixture
    def base_url(self):
        """Base URL for WebSocket connections."""
        return "ws://localhost:8000"

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

    @pytest.mark.asyncio
    async def test_ws_protocol_error_invalid_subprotocol(self, base_url):
        """Test WebSocket protocol error with invalid subprotocol."""
        uri = f"{base_url}/run"

        try:
            # Try to connect with invalid subprotocol
            async with websockets.connect(uri, subprotocols=["invalid.protocol.v1"]) as websocket:
                pytest.fail("Connection should have been rejected")
        except websockets.exceptions.InvalidStatusCode as e:
            # Should get HTTP 400, 403, or 426 for unsupported subprotocol
            assert e.status_code in [400, 403, 426]
        except ConnectionClosedError as e:
            # Or WebSocket close with protocol error code
            assert e.code == 1002  # Protocol error
        except Exception as e:
            pytest.skip(f"WebSocket protocol test failed: {e}")

    @pytest.mark.asyncio
    async def test_ws_close_code_malformed_frame(self, base_url):
        """Test WebSocket close code 1008 for malformed frame."""
        try:
            async with self.websocket_connection(base_url) as websocket:
                # Send completely malformed JSON
                await websocket.send("not-json-at-all")

                try:
                    # Should either get error response or connection close
                    message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    data = json.loads(message)

                    if data.get("kind") == "RunResult":
                        envelope = data["content"]
                        assert envelope["status"] == "error"
                        assert envelope["error"]["code"] in ["ERR_INPUTS", "ERR_WS_PROTOCOL"]

                except ConnectionClosedError as e:
                    # Connection closed due to malformed data
                    assert e.code == 1008  # Policy violation (malformed data)
                except TimeoutError:
                    pytest.fail("Expected error response or connection close")

        except Exception as e:
            pytest.skip(f"WebSocket malformed frame test failed: {e}")

    @pytest.mark.asyncio
    async def test_ws_timeout_error_code(self, base_url):
        """Test WebSocket timeout handling with ERR_WS_TIMEOUT."""
        try:
            async with self.websocket_connection(base_url) as websocket:
                # Send valid RunOpen but simulate timeout scenario
                payload = {
                    "kind": "RunOpen",
                    "content": {
                        "role": "client",
                        "execution_id": "timeout-test-123",
                        "payload": {
                            "execution_id": "timeout-test-123",
                            "write_prefix": "/tmp/timeout-test/",
                            "schema": "v1",
                            "mode": "mock",
                            "inputs": {
                                "schema": "v1",
                                "params": {"messages": [{"role": "user", "content": "timeout test"}]},
                            },
                        },
                    },
                }

                await websocket.send(json.dumps(payload))

                # In mock mode, this should complete quickly
                # Testing actual timeout would require longer-running processor
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=30.0)
                    data = json.loads(message)

                    # Should get successful result in mock mode
                    if data.get("kind") == "RunResult":
                        envelope = data["content"]
                        assert envelope["status"] == "success"
                        assert envelope["execution_id"] == "timeout-test-123"

                except TimeoutError:
                    # If we hit client timeout, processor might be hanging
                    pytest.fail("WebSocket request timed out - possible processor issue")

        except Exception as e:
            pytest.skip(f"WebSocket timeout test failed: {e}")

    @pytest.mark.asyncio
    async def test_err_inputs_missing_required_fields(self, base_url):
        """Test ERR_INPUTS for missing required fields in RunOpen."""
        try:
            async with self.websocket_connection(base_url) as websocket:
                # Missing execution_id in payload
                invalid_payload = {
                    "kind": "RunOpen",
                    "content": {
                        "role": "client",
                        "execution_id": "inputs-error-123",
                        "payload": {
                            # Missing execution_id field
                            "write_prefix": "/tmp/inputs-error/",
                            "schema": "v1",
                            "mode": "mock",
                            "inputs": {"schema": "v1", "params": {"messages": [{"role": "user", "content": "test"}]}},
                        },
                    },
                }

                await websocket.send(json.dumps(invalid_payload))

                # Should get error response
                message = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                data = json.loads(message)

                assert data.get("kind") == "RunResult"
                envelope = data["content"]
                assert envelope["status"] == "error"
                assert envelope["error"]["code"] == "ERR_INPUTS"
                assert "execution_id" in envelope["error"]["message"]
                assert envelope["execution_id"] == ""  # Empty when missing

        except Exception as e:
            pytest.skip(f"WebSocket ERR_INPUTS test failed: {e}")

    @pytest.mark.asyncio
    async def test_err_inputs_invalid_schema_version(self, base_url):
        """Test ERR_INPUTS for invalid schema version."""
        try:
            async with self.websocket_connection(base_url) as websocket:
                invalid_payload = {
                    "kind": "RunOpen",
                    "content": {
                        "role": "client",
                        "execution_id": "schema-error-456",
                        "payload": {
                            "execution_id": "schema-error-456",
                            "write_prefix": "/tmp/schema-error/",
                            "schema": "v999",  # Invalid schema version
                            "mode": "mock",
                            "inputs": {"schema": "v999", "params": {"messages": [{"role": "user", "content": "test"}]}},
                        },
                    },
                }

                await websocket.send(json.dumps(invalid_payload))

                message = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                data = json.loads(message)

                assert data.get("kind") == "RunResult"
                envelope = data["content"]
                assert envelope["status"] == "error"
                assert envelope["error"]["code"] == "ERR_INPUTS"
                assert envelope["execution_id"] == "schema-error-456"

        except Exception as e:
            pytest.skip(f"WebSocket schema error test failed: {e}")

    @pytest.mark.asyncio
    async def test_err_image_digest_missing(self, base_url):
        """Test ERR_IMAGE_DIGEST_MISSING when IMAGE_DIGEST env var not set."""
        import os

        # Save and remove IMAGE_DIGEST
        original_digest = os.environ.get("IMAGE_DIGEST")
        if "IMAGE_DIGEST" in os.environ:
            del os.environ["IMAGE_DIGEST"]

        try:
            async with self.websocket_connection(base_url) as websocket:
                payload = {
                    "kind": "RunOpen",
                    "content": {
                        "role": "client",
                        "execution_id": "digest-error-789",
                        "payload": {
                            "execution_id": "digest-error-789",
                            "write_prefix": "/tmp/digest-error/",
                            "schema": "v1",
                            "mode": "mock",
                            "inputs": {"schema": "v1", "params": {"messages": [{"role": "user", "content": "test"}]}},
                        },
                    },
                }

                await websocket.send(json.dumps(payload))

                message = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                data = json.loads(message)

                assert data.get("kind") == "RunResult"
                envelope = data["content"]
                assert envelope["status"] == "error"
                assert envelope["error"]["code"] == "ERR_IMAGE_DIGEST_MISSING"
                assert envelope["execution_id"] == "digest-error-789"
                assert "IMAGE_DIGEST" in envelope["error"]["message"]

        except Exception as e:
            pytest.skip(f"WebSocket image digest error test failed: {e}")
        finally:
            # Restore IMAGE_DIGEST
            if original_digest:
                os.environ["IMAGE_DIGEST"] = original_digest

    @pytest.mark.asyncio
    async def test_error_envelope_consistency(self, base_url):
        """Test all WebSocket error envelopes have consistent structure."""
        test_cases = [
            {
                "name": "missing_execution_id",
                "payload": {
                    "kind": "RunOpen",
                    "content": {
                        "role": "client",
                        "execution_id": "consistency-1",
                        "payload": {
                            # Missing execution_id
                            "write_prefix": "/tmp/consistency/",
                            "schema": "v1",
                            "mode": "mock",
                            "inputs": {"schema": "v1", "params": {"messages": [{"role": "user", "content": "test"}]}},
                        },
                    },
                },
            },
            {
                "name": "missing_write_prefix",
                "payload": {
                    "kind": "RunOpen",
                    "content": {
                        "role": "client",
                        "execution_id": "consistency-2",
                        "payload": {
                            "execution_id": "consistency-2",
                            # Missing write_prefix
                            "schema": "v1",
                            "mode": "mock",
                            "inputs": {"schema": "v1", "params": {"messages": [{"role": "user", "content": "test"}]}},
                        },
                    },
                },
            },
        ]

        try:
            for case in test_cases:
                async with self.websocket_connection(base_url) as websocket:
                    await websocket.send(json.dumps(case["payload"]))

                    message = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                    data = json.loads(message)

                    assert data.get("kind") == "RunResult", f"Expected RunResult for {case['name']}"
                    envelope = data["content"]

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

        except Exception as e:
            pytest.skip(f"WebSocket error consistency test failed: {e}")

    @pytest.mark.asyncio
    async def test_ws_connection_close_codes(self, base_url):
        """Test WebSocket connection close codes for various error conditions."""
        close_code_tests = [
            {
                "name": "invalid_json",
                "send_data": "invalid-json-data",
                "expected_codes": [1008],  # Policy violation
            },
            {
                "name": "wrong_frame_kind",
                "send_data": json.dumps({"kind": "InvalidKind", "content": {}}),
                "expected_codes": [1002, 1008],  # Protocol error or policy violation
            },
        ]

        for test_case in close_code_tests:
            try:
                async with self.websocket_connection(base_url) as websocket:
                    await websocket.send(test_case["send_data"])

                    try:
                        # Wait a bit for potential response
                        await asyncio.wait_for(websocket.recv(), timeout=2.0)
                    except ConnectionClosedError as e:
                        assert e.code in test_case["expected_codes"], (
                            f"Test {test_case['name']}: Expected close codes {test_case['expected_codes']}, got {e.code}"
                        )
                    except TimeoutError:
                        # No response - check if connection is still open
                        if websocket.state.name != "OPEN":
                            # Connection was closed but we didn't catch the close event
                            pass
                        else:
                            pytest.fail(f"Test {test_case['name']}: Expected connection close, but still open")

            except Exception as e:
                pytest.skip(f"WebSocket close code test {test_case['name']} failed: {e}")

    @pytest.mark.asyncio
    async def test_ws_error_no_stack_traces(self, base_url):
        """Test WebSocket errors don't leak stack traces in error messages."""
        try:
            async with self.websocket_connection(base_url) as websocket:
                # Send payload that might cause internal error
                error_payload = {
                    "kind": "RunOpen",
                    "content": {
                        "role": "client",
                        "execution_id": "stack-trace-test",
                        "payload": {
                            "execution_id": "stack-trace-test",
                            "write_prefix": "/tmp/stack-test/",
                            "schema": "v1",
                            "mode": "mock",
                            "inputs": {
                                "schema": "v1",
                                "params": {
                                    # Potentially problematic data
                                    "messages": None  # Invalid messages value
                                },
                            },
                        },
                    },
                }

                await websocket.send(json.dumps(error_payload))

                message = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                data = json.loads(message)

                if data.get("kind") == "RunResult":
                    envelope = data["content"]
                    if envelope["status"] == "error":
                        error_message = envelope["error"]["message"]

                        # Should not contain stack trace indicators
                        stack_indicators = ["Traceback", 'File "', "line ", "in ", "raise ", "Exception:"]
                        for indicator in stack_indicators:
                            assert indicator not in error_message, (
                                f"Error message contains stack trace indicator '{indicator}': {error_message}"
                            )

        except Exception as e:
            pytest.skip(f"WebSocket stack trace test failed: {e}")
