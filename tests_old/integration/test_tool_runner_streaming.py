"""Integration tests for ToolRunner streaming."""

import pytest
from tests.helpers import invoke_processor


@pytest.mark.integration
@pytest.mark.requires_docker
class TestToolRunnerStreaming:
    """Test streaming functionality in orchestration flow."""

    def test_invoke_non_streaming_mode(self):
        """Test invocation with stream=False returns final envelope."""
        envelope = invoke_processor(
            "llm/litellm@1",
            inputs={
                "schema": "v1",
                "params": {"messages": [{"role": "user", "content": "streaming test"}]},
            },
            stream=False,
        )

        assert envelope["status"] == "success"
        assert "execution_id" in envelope
        assert "outputs" in envelope

    def test_invoke_streaming_returns_final_envelope(self):
        """Test streaming mode ultimately returns final envelope."""
        from apps.core.tool_runner import ToolRunner

        orch = ToolRunner()

        result = orch.invoke(
            ref="llm/litellm@1",
            mode="mock",
            inputs={
                "schema": "v1",
                "params": {"messages": [{"role": "user", "content": "test"}]},
            },
            build=True,
            stream=True,
            timeout_s=120,
            write_prefix="/artifacts/outputs/test/{execution_id}/",
            world_facet="artifacts",
            adapter="local",
        )

        # Streaming mode returns generator or final envelope
        if hasattr(result, "__iter__") and not isinstance(result, dict):
            # Collect all events
            events = list(result)
            # Should have at least one event
            assert len(events) > 0
            # Events should be dicts with kind/content
            for event in events:
                assert isinstance(event, dict)
                assert "kind" in event or "status" in event
        else:
            # Non-streaming, just validate envelope
            assert result["status"] == "success"
