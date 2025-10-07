"""WebSocket protocol contract tests (direct processor WS testing)."""

import asyncio
import json
import pytest
import websockets
from websockets.exceptions import ConnectionClosedError, InvalidStatus

from tests.helpers import build_ws_payload
from tests.tools.localctl_helpers import get_ws_url


# Container started by Makefile via `localctl start --ref llm/litellm@1`
WS_URL = get_ws_url("llm/litellm@1").replace("/run", "")  # Base URL without /run


@pytest.mark.contracts
@pytest.mark.requires_docker
class TestWebSocketProtocol:
    """Test raw WebSocket protocol (theory.run.v1 subprotocol)."""

    @pytest.mark.asyncio
    async def test_websocket_connection_establishes_with_subprotocol(self):
        """Test WebSocket connection establishes with theory.run.v1 subprotocol."""
        uri = f"{WS_URL}/run"

        async with websockets.connect(uri, subprotocols=["theory.run.v1"]) as websocket:
            assert websocket.subprotocol == "theory.run.v1"
            assert websocket.state.name == "OPEN"

    @pytest.mark.asyncio
    async def test_websocket_invalid_subprotocol_rejected(self):
        """Test WebSocket connection with invalid subprotocol is rejected."""
        uri = f"{WS_URL}/run"

        try:
            async with websockets.connect(uri, subprotocols=["invalid.protocol"]) as websocket:
                pytest.fail("Connection should have been rejected with invalid subprotocol")
        except InvalidStatus as e:
            assert e.response.status_code in [400, 403, 426]
        except ConnectionClosedError as e:
            assert e.code in [1002, 1008]  # Protocol error or policy violation

    @pytest.mark.asyncio
    async def test_websocket_run_invoke_frame_structure(self):
        """Test RunOpen frame accepts correct structure and returns RunResult."""
        uri = f"{WS_URL}/run"

        execution_id = "test-protocol-123"
        write_prefix = f"/artifacts/outputs/test/{execution_id}/"

        inputs = {
            "schema": "v1",
            "params": {"messages": [{"role": "user", "content": "protocol test"}]},
        }

        payload = build_ws_payload(
            ref="llm/litellm@1",
            execution_id=execution_id,
            write_prefix=write_prefix,
            mode="mock",
            inputs=inputs,
        )

        async with websockets.connect(uri, subprotocols=["theory.run.v1"]) as websocket:
            await websocket.send(json.dumps(payload))

            # Collect messages until RunResult
            for _ in range(50):
                message = await asyncio.wait_for(websocket.recv(), timeout=30.0)
                data = json.loads(message)

                if data.get("kind") == "RunResult":
                    envelope = data["content"]
                    assert envelope["status"] == "success"
                    assert envelope["execution_id"] == execution_id
                    assert "outputs" in envelope
                    assert "meta" in envelope
                    return

            pytest.fail("No RunResult received")

    @pytest.mark.asyncio
    async def test_websocket_malformed_frame_handling(self):
        """Test malformed frames trigger appropriate error responses."""
        uri = f"{WS_URL}/run"

        async with websockets.connect(uri, subprotocols=["theory.run.v1"]) as websocket:
            # Send malformed frame
            malformed = {
                "kind": "RunInvoke",
                "content": {
                    # Missing required fields
                    "mode": "mock"
                },
            }

            await websocket.send(json.dumps(malformed))

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

    @pytest.mark.asyncio
    async def test_websocket_connection_timeout_handling(self):
        """Test WebSocket connection handles timeouts gracefully."""
        uri = f"{WS_URL}/run"

        async with websockets.connect(uri, subprotocols=["theory.run.v1"]) as websocket:
            # Don't send anything, just wait
            try:
                await asyncio.wait_for(websocket.recv(), timeout=1.0)
            except TimeoutError:
                # Expected - no message sent
                pass

            # Connection should still be open
            assert websocket.state.name == "OPEN"
