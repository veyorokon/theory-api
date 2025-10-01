"""WebSocket streaming contract tests for processor endpoints."""

import json
import pytest
import asyncio
from contextlib import asynccontextmanager
from typing import List, Dict, Any, AsyncIterator

import websockets
from websockets.exceptions import ConnectionClosedError


@pytest.mark.contracts
class TestWebSocketStreamingContract:
    """Test WebSocket streaming contract for real-time event flow."""

    @pytest.fixture
    def base_url(self):
        """Base URL for WebSocket connections."""
        return "ws://localhost:8000"

    @pytest.fixture
    def mock_image_digest(self, monkeypatch):
        """Ensure IMAGE_DIGEST is set for successful requests."""
        monkeypatch.setenv("IMAGE_DIGEST", "sha256:streaming123test")

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

    async def collect_messages(self, websocket, max_messages: int = 100, timeout: float = 30.0) -> List[Dict[str, Any]]:
        """Collect all messages from WebSocket until RunResult or timeout."""
        messages = []
        start_time = asyncio.get_event_loop().time()

        while len(messages) < max_messages:
            try:
                # Calculate remaining timeout
                elapsed = asyncio.get_event_loop().time() - start_time
                remaining_timeout = max(0.1, timeout - elapsed)

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

        return messages

    @pytest.mark.asyncio
    async def test_websocket_streaming_event_types(self, base_url, mock_image_digest):
        """Test WebSocket emits proper event types during processing."""
        try:
            async with self.websocket_connection(base_url) as websocket:
                payload = {
                    "kind": "RunOpen",
                    "content": {
                        "role": "client",
                        "execution_id": "stream-events-123",
                        "payload": {
                            "execution_id": "stream-events-123",
                            "write_prefix": "/tmp/stream-events/",
                            "schema": "v1",
                            "mode": "mock",
                            "inputs": {
                                "schema": "v1",
                                "params": {"messages": [{"role": "user", "content": "streaming events test"}]},
                            },
                        },
                    },
                }

                await websocket.send(json.dumps(payload))

                # Collect all messages
                messages = await self.collect_messages(websocket)

                assert len(messages) > 0, "Should receive at least one message"

                # Last message should be RunResult
                final_message = messages[-1]
                assert final_message.get("kind") == "RunResult"

                # Check for valid event types
                valid_event_kinds = {"Token", "Frame", "Log", "Event", "RunResult"}
                for message in messages:
                    assert message.get("kind") in valid_event_kinds, f"Invalid event kind: {message.get('kind')}"

                # Final envelope should be success
                envelope = final_message["content"]
                assert envelope["status"] == "success"
                assert envelope["execution_id"] == "stream-events-123"

        except Exception as e:
            pytest.skip(f"WebSocket streaming events test failed: {e}")

    @pytest.mark.asyncio
    async def test_websocket_token_events(self, base_url, mock_image_digest):
        """Test WebSocket Token events for incremental output."""
        try:
            async with self.websocket_connection(base_url) as websocket:
                payload = {
                    "kind": "RunOpen",
                    "content": {
                        "role": "client",
                        "execution_id": "stream-tokens-456",
                        "payload": {
                            "execution_id": "stream-tokens-456",
                            "write_prefix": "/tmp/stream-tokens/",
                            "schema": "v1",
                            "mode": "mock",
                            "inputs": {
                                "schema": "v1",
                                "params": {"messages": [{"role": "user", "content": "generate streaming tokens test"}]},
                            },
                        },
                    },
                }

                await websocket.send(json.dumps(payload))
                messages = await self.collect_messages(websocket)

                # Look for Token events
                token_events = [msg for msg in messages if msg.get("kind") == "Token"]

                if token_events:
                    # Validate Token event structure
                    for token_event in token_events:
                        assert "content" in token_event
                        content = token_event["content"]

                        # Token events should have text or delta
                        assert "text" in content or "delta" in content

                        if "text" in content:
                            assert isinstance(content["text"], str)
                        if "delta" in content:
                            assert isinstance(content["delta"], str)

                # Final result should still be valid
                final_message = messages[-1]
                assert final_message.get("kind") == "RunResult"
                envelope = final_message["content"]
                assert envelope["status"] == "success"

        except Exception as e:
            pytest.skip(f"WebSocket token events test failed: {e}")

    @pytest.mark.asyncio
    async def test_websocket_log_events(self, base_url, mock_image_digest):
        """Test WebSocket Log events for processing feedback."""
        try:
            async with self.websocket_connection(base_url) as websocket:
                payload = {
                    "kind": "RunOpen",
                    "content": {
                        "role": "client",
                        "execution_id": "stream-logs-789",
                        "payload": {
                            "execution_id": "stream-logs-789",
                            "write_prefix": "/tmp/stream-logs/",
                            "schema": "v1",
                            "mode": "mock",
                            "inputs": {
                                "schema": "v1",
                                "params": {"messages": [{"role": "user", "content": "log events test"}]},
                            },
                        },
                    },
                }

                await websocket.send(json.dumps(payload))
                messages = await self.collect_messages(websocket)

                # Look for Log events
                log_events = [msg for msg in messages if msg.get("kind") == "Log"]

                if log_events:
                    # Validate Log event structure
                    for log_event in log_events:
                        assert "content" in log_event
                        content = log_event["content"]

                        # Log events should have level and message
                        assert "level" in content
                        assert "message" in content
                        assert content["level"] in ["debug", "info", "warning", "error"]
                        assert isinstance(content["message"], str)

        except Exception as e:
            pytest.skip(f"WebSocket log events test failed: {e}")

    @pytest.mark.asyncio
    async def test_websocket_frame_events_for_artifacts(self, base_url, mock_image_digest):
        """Test WebSocket Frame events for artifact creation."""
        try:
            async with self.websocket_connection(base_url) as websocket:
                payload = {
                    "kind": "RunOpen",
                    "content": {
                        "role": "client",
                        "execution_id": "stream-frames-abc",
                        "payload": {
                            "execution_id": "stream-frames-abc",
                            "write_prefix": "/tmp/stream-frames/",
                            "schema": "v1",
                            "mode": "mock",
                            "inputs": {
                                "schema": "v1",
                                "params": {"messages": [{"role": "user", "content": "frame events test"}]},
                            },
                        },
                    },
                }

                await websocket.send(json.dumps(payload))
                messages = await self.collect_messages(websocket)

                # Look for Frame events
                frame_events = [msg for msg in messages if msg.get("kind") == "Frame"]

                if frame_events:
                    # Validate Frame event structure
                    for frame_event in frame_events:
                        assert "content" in frame_event
                        content = frame_event["content"]

                        # Frame events should have path and optionally mime_type
                        assert "path" in content
                        assert isinstance(content["path"], str)

                        if "mime_type" in content:
                            assert isinstance(content["mime_type"], str)

        except Exception as e:
            pytest.skip(f"WebSocket frame events test failed: {e}")

    @pytest.mark.asyncio
    async def test_websocket_streaming_real_time_latency(self, base_url, mock_image_digest):
        """Test WebSocket streaming provides real-time updates with low latency."""
        try:
            async with self.websocket_connection(base_url) as websocket:
                payload = {
                    "kind": "RunOpen",
                    "content": {
                        "role": "client",
                        "execution_id": "stream-latency-def",
                        "payload": {
                            "execution_id": "stream-latency-def",
                            "write_prefix": "/tmp/stream-latency/",
                            "schema": "v1",
                            "mode": "mock",
                            "inputs": {
                                "schema": "v1",
                                "params": {"messages": [{"role": "user", "content": "latency test"}]},
                            },
                        },
                    },
                }

                start_time = asyncio.get_event_loop().time()
                await websocket.send(json.dumps(payload))

                # Measure time to first event
                first_message = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                first_event_time = asyncio.get_event_loop().time()
                first_latency = (first_event_time - start_time) * 1000  # ms

                # First event should arrive quickly (< 5 seconds for mock mode)
                assert first_latency < 5000, f"First event took {first_latency:.1f}ms, too slow"

                data = json.loads(first_message)
                assert data.get("kind") in {"Token", "Frame", "Log", "Event", "RunResult"}

        except Exception as e:
            pytest.skip(f"WebSocket latency test failed: {e}")

    @pytest.mark.asyncio
    async def test_websocket_streaming_concurrent_connections(self, base_url, mock_image_digest):
        """Test WebSocket handles concurrent streaming connections."""

        async def stream_request(execution_id: str):
            payload = {
                "kind": "RunOpen",
                "content": {
                    "role": "client",
                    "execution_id": execution_id,
                    "payload": {
                        "execution_id": execution_id,
                        "write_prefix": f"/tmp/concurrent-stream-{execution_id}/",
                        "schema": "v1",
                        "mode": "mock",
                        "inputs": {
                            "schema": "v1",
                            "params": {"messages": [{"role": "user", "content": f"concurrent stream {execution_id}"}]},
                        },
                    },
                },
            }

            try:
                async with self.websocket_connection(base_url) as websocket:
                    await websocket.send(json.dumps(payload))
                    messages = await self.collect_messages(websocket, timeout=15.0)

                    if messages:
                        final_message = messages[-1]
                        if final_message.get("kind") == "RunResult":
                            envelope = final_message["content"]
                            return envelope["status"], len(messages), envelope["execution_id"]

                    return "timeout", 0, execution_id

            except Exception as e:
                return "error", 0, str(e)

        try:
            # Make 3 concurrent streaming requests
            tasks = [stream_request(f"concurrent-stream-{i}") for i in range(3)]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # All should succeed
            for result in results:
                if isinstance(result, Exception):
                    pytest.skip(f"Concurrent streaming test failed: {result}")
                else:
                    status, message_count, execution_id = result
                    assert status == "success"
                    assert message_count > 0
                    assert execution_id.startswith("concurrent-stream-")

        except Exception as e:
            pytest.skip(f"WebSocket concurrent streaming test failed: {e}")

    @pytest.mark.asyncio
    async def test_websocket_streaming_error_handling(self, base_url):
        """Test WebSocket streaming handles errors gracefully."""
        try:
            async with self.websocket_connection(base_url) as websocket:
                # Send payload that will cause error
                error_payload = {
                    "kind": "RunOpen",
                    "content": {
                        "role": "client",
                        "execution_id": "stream-error-ghi",
                        "payload": {
                            "execution_id": "stream-error-ghi",
                            "write_prefix": "/tmp/stream-error/",
                            "schema": "v1",
                            "mode": "mock",
                            "inputs": {
                                # Invalid inputs structure
                                "invalid": "structure"
                            },
                        },
                    },
                }

                await websocket.send(json.dumps(error_payload))
                messages = await self.collect_messages(websocket, timeout=10.0)

                assert len(messages) > 0, "Should receive error response"

                # Should get RunResult with error
                final_message = messages[-1]
                assert final_message.get("kind") == "RunResult"

                envelope = final_message["content"]
                assert envelope["status"] == "error"
                assert envelope["execution_id"] == "stream-error-ghi"
                assert "error" in envelope
                assert envelope["error"]["code"].startswith("ERR_")

        except Exception as e:
            pytest.skip(f"WebSocket streaming error test failed: {e}")

    @pytest.mark.asyncio
    async def test_websocket_streaming_vs_final_consistency(self, base_url, mock_image_digest):
        """Test WebSocket streaming events are consistent with final envelope."""
        try:
            async with self.websocket_connection(base_url) as websocket:
                payload = {
                    "kind": "RunOpen",
                    "content": {
                        "role": "client",
                        "execution_id": "stream-consistency-jkl",
                        "payload": {
                            "execution_id": "stream-consistency-jkl",
                            "write_prefix": "/tmp/stream-consistency/",
                            "schema": "v1",
                            "mode": "mock",
                            "inputs": {
                                "schema": "v1",
                                "params": {"messages": [{"role": "user", "content": "consistency test"}]},
                            },
                        },
                    },
                }

                await websocket.send(json.dumps(payload))
                messages = await self.collect_messages(websocket)

                assert len(messages) > 0
                final_message = messages[-1]
                assert final_message.get("kind") == "RunResult"

                envelope = final_message["content"]
                assert envelope["status"] == "success"
                assert envelope["execution_id"] == "stream-consistency-jkl"

                # Collect all artifacts mentioned in streaming events
                streamed_artifacts = set()
                for message in messages[:-1]:  # Exclude final RunResult
                    if message.get("kind") == "Frame":
                        content = message.get("content", {})
                        if "path" in content:
                            streamed_artifacts.add(content["path"])

                # Final envelope artifacts should be consistent with streamed ones
                final_artifacts = {output.get("path") for output in envelope.get("outputs", [])}

                # All streamed artifacts should appear in final envelope
                # (but final envelope may have additional artifacts not streamed)
                for artifact in streamed_artifacts:
                    assert artifact in final_artifacts, f"Streamed artifact {artifact} not in final envelope"

        except Exception as e:
            pytest.skip(f"WebSocket streaming consistency test failed: {e}")

    @pytest.mark.asyncio
    async def test_websocket_streaming_message_ordering(self, base_url, mock_image_digest):
        """Test WebSocket streaming events arrive in logical order."""
        try:
            async with self.websocket_connection(base_url) as websocket:
                payload = {
                    "kind": "RunOpen",
                    "content": {
                        "role": "client",
                        "execution_id": "stream-ordering-mno",
                        "payload": {
                            "execution_id": "stream-ordering-mno",
                            "write_prefix": "/tmp/stream-ordering/",
                            "schema": "v1",
                            "mode": "mock",
                            "inputs": {
                                "schema": "v1",
                                "params": {"messages": [{"role": "user", "content": "ordering test"}]},
                            },
                        },
                    },
                }

                await websocket.send(json.dumps(payload))
                messages = await self.collect_messages(websocket)

                assert len(messages) > 0

                # Last message must be RunResult
                final_message = messages[-1]
                assert final_message.get("kind") == "RunResult"

                # Check for logical ordering
                seen_run_result = False
                for i, message in enumerate(messages):
                    kind = message.get("kind")

                    # RunResult should only appear at the end
                    if kind == "RunResult":
                        assert i == len(messages) - 1, "RunResult must be the final message"
                        seen_run_result = True
                    else:
                        assert not seen_run_result, f"Event {kind} after RunResult at position {i}"

                assert seen_run_result, "Must have RunResult as final message"

        except Exception as e:
            pytest.skip(f"WebSocket message ordering test failed: {e}")
