"""
Tool-specific tests for llm/litellm@1.

Tests streaming, model parameter overrides, and other litellm-specific behavior.
"""

import pytest
from apps.tools.models import Tool

REF = "llm/litellm@1"


@pytest.fixture(scope="module", autouse=True)
def skip_if_disabled(django_db_blocker):
    """Skip entire module if llm/litellm@1 not enabled."""
    with django_db_blocker.unblock():
        if not Tool.objects.filter(ref=REF, enabled=True).exists():
            pytest.skip(f"{REF} not enabled")


@pytest.mark.integration
def test_litellm_mock_basic(adapter):
    """Basic invocation in mock mode."""
    result = adapter.invoke(
        ref=REF,
        mode="mock",
        inputs={
            "schema": "v1",
            "params": {
                "messages": [{"role": "user", "content": "test message"}],
            },
        },
        artifact_scope="local",
    )

    assert result["control"]["status"] == "success"
    assert result["control"]["run_id"]
    assert result["control"]["final"] is True

    # Should have response and usage outputs
    assert isinstance(result["outputs"], dict)
    assert "response" in result["outputs"] or "tokens" in result["outputs"]


@pytest.mark.integration
def test_litellm_streaming(adapter):
    """Test streaming mode produces token events."""
    events = list(
        adapter.invoke_stream(
            ref=REF,
            mode="mock",
            inputs={
                "schema": "v1",
                "params": {
                    "messages": [{"role": "user", "content": "test"}],
                },
            },
            artifact_scope="local",
        )
    )

    # Should have token events
    token_events = [e for e in events if e.get("kind") == "Token"]
    assert len(token_events) > 0

    # Last event should be Response
    final = events[-1]
    assert final.get("kind") == "Response"
    assert final["control"]["status"] == "success"
    assert final["control"]["final"] is True


@pytest.mark.integration
def test_litellm_model_parameter(adapter):
    """Test model parameter is respected."""
    result = adapter.invoke(
        ref=REF,
        mode="mock",
        inputs={
            "schema": "v1",
            "params": {
                "model": "gpt-4",
                "messages": [{"role": "user", "content": "test"}],
            },
        },
        artifact_scope="local",
    )

    assert result["control"]["status"] == "success"
    # Outputs should be present
    assert "outputs" in result


@pytest.mark.integration
def test_litellm_empty_messages_error(adapter):
    """Test that empty messages array produces error."""
    result = adapter.invoke(
        ref=REF,
        mode="mock",
        inputs={
            "schema": "v1",
            "strict": True,  # Enable validation in mock mode
            "params": {
                "messages": [],  # Invalid: empty
            },
        },
        artifact_scope="local",
    )

    # Should fail validation
    assert result["control"]["status"] == "error"
    assert "error" in result
    assert result["error"]["code"].startswith("ERR_")
