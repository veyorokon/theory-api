"""Write prefix expansion contract tests (WebSocket + Docker)."""

import asyncio
import json
import os
import pytest
import websockets

from tests.tools.docker_fixtures import processor_container
from tests.helpers import build_ws_payload


@pytest.mark.contracts
@pytest.mark.requires_docker
class TestWritePrefixExpansion:
    """Test write_prefix {{execution_id}} expansion and validation via WebSocket."""

    @pytest.fixture
    def mock_image_digest(self, monkeypatch):
        # Enforce digest is present (processor container has IMAGE_DIGEST set)
        monkeypatch.setenv("IMAGE_DIGEST", "sha256:deadbeef")

    async def _ws_invoke(self, ws_url: str, execution_id: str, write_prefix: str) -> dict:
        """Invoke processor via WebSocket and return final envelope."""
        inputs = {
            "schema": "v1",
            "params": {
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "test"}],
            },
        }

        # Use helper to build complete payload with presigned URLs
        payload = build_ws_payload(
            ref="llm/litellm@1",
            execution_id=execution_id,
            write_prefix=write_prefix,
            mode="mock",
            inputs=inputs,
        )

        async with websockets.connect(f"{ws_url}/run", subprotocols=["theory.run.v1"]) as ws:
            await ws.send(json.dumps(payload))

            # Receive Ack
            ack_msg = await ws.recv()
            ack = json.loads(ack_msg)
            assert ack.get("kind") == "Ack", f"Expected Ack, got {ack.get('kind')}"

            # Receive events until RunResult
            for _ in range(50):
                msg = await asyncio.wait_for(ws.recv(), timeout=30.0)
                data = json.loads(msg)
                if data.get("kind") == "RunResult":
                    return data["content"]

            raise RuntimeError("No RunResult received within 50 messages")

    def _assert_expanded(self, envelope: dict, expected_prefix: str):
        # Outputs must live under expanded prefix
        assert envelope["status"] == "success"
        for out in envelope.get("outputs", []):
            path = out.get("path", "")
            assert path.startswith(expected_prefix), f"{path} !startswith {expected_prefix}"
            assert "{{execution_id}}" not in path

        # Index must live under expanded prefix
        index_path = envelope.get("index_path", "")
        assert index_path.startswith(expected_prefix), f"{index_path} !startswith {expected_prefix}"
        assert "{{execution_id}}" not in index_path

    def test_basic_expansion(self, processor_container, mock_image_digest):
        execution_id = "wp-basic-001"
        write_prefix = "/artifacts/outputs/{{execution_id}}/"

        async def run():
            return await self._ws_invoke(processor_container["ws_url"], execution_id, write_prefix)

        env = asyncio.run(run())
        expected = f"/artifacts/outputs/{execution_id}/"
        self._assert_expanded(env, expected)

    def test_multiple_placeholders(self, processor_container, mock_image_digest):
        execution_id = "wp-multi-002"
        # Appears twice; both must expand
        write_prefix = "/artifacts/{{execution_id}}/nested/{{execution_id}}/"

        async def run():
            return await self._ws_invoke(processor_container["ws_url"], execution_id, write_prefix)

        env = asyncio.run(run())
        expected = f"/artifacts/{execution_id}/nested/{execution_id}/"
        self._assert_expanded(env, expected)

    def test_case_sensitivity(self, processor_container, mock_image_digest):
        execution_id = "CaseSensitive-XYZ"
        write_prefix = "/artifacts/cs/{{execution_id}}/out/"

        async def run():
            return await self._ws_invoke(processor_container["ws_url"], execution_id, write_prefix)

        env = asyncio.run(run())
        expected = f"/artifacts/cs/{execution_id}/out/"
        self._assert_expanded(env, expected)

    def test_special_characters(self, processor_container, mock_image_digest):
        execution_id = "test-123_456.789"
        write_prefix = "/artifacts/sp/{{execution_id}}/"

        async def run():
            return await self._ws_invoke(processor_container["ws_url"], execution_id, write_prefix)

        env = asyncio.run(run())
        expected = f"/artifacts/sp/{execution_id}/"
        self._assert_expanded(env, expected)

    def test_trailing_slash_normalization(self, processor_container, mock_image_digest):
        execution_id = "wp-slash-003"
        # No trailing slash; handler should normalize to include one
        write_prefix = "/artifacts/trail/{{execution_id}}"

        async def run():
            return await self._ws_invoke(processor_container["ws_url"], execution_id, write_prefix)

        env = asyncio.run(run())
        expected = f"/artifacts/trail/{execution_id}/"
        self._assert_expanded(env, expected)

    def test_static_prefix_allowed(self, processor_container, mock_image_digest):
        execution_id = "wp-static-004"
        # No placeholder: allowed; nothing to expand
        static_prefix = "/artifacts/static/output/path/"

        async def run():
            return await self._ws_invoke(processor_container["ws_url"], execution_id, static_prefix)

        env = asyncio.run(run())
        # Even with a static prefix, outputs/index must live under that prefix
        for out in env.get("outputs", []):
            assert out["path"].startswith(static_prefix)
        assert env.get("index_path", "").startswith(static_prefix)

    def test_consistency_across_all_artifacts(self, processor_container, mock_image_digest):
        execution_id = "wp-consistent-005"
        # One placeholder, nested path
        write_prefix = "/artifacts/consistent/{{execution_id}}/test/"

        async def run():
            return await self._ws_invoke(processor_container["ws_url"], execution_id, write_prefix)

        env = asyncio.run(run())
        expected = f"/artifacts/consistent/{execution_id}/test/"
        self._assert_expanded(env, expected)
