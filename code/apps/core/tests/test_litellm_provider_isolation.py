"""
Tests for LiteLLM provider test isolation.

Ensures no global state contamination between test runs.
"""

import litellm
import pytest
from apps.core.integrations.litellm_provider import LiteLLMProvider


def test_provider_does_not_mutate_global_api_base(monkeypatch):
    """Provider should not mutate global litellm.api_base state."""
    # Arrange: start from a known global
    orig = getattr(litellm, "api_base", None)
    monkeypatch.setattr(litellm, "api_base", "SHOULD_NOT_CHANGE", raising=False)

    # Act: create provider with a custom base and perform a call (mocked)
    calls = {}

    def fake_completion(*args, **kwargs):
        calls["kwargs"] = kwargs
        # minimal shape that LiteLLMProvider expects
        return {
            "choices": [{"message": {"content": "mocked response"}}],
            "model": "test-model",
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }

    monkeypatch.setattr(litellm, "completion", fake_completion)
    provider = LiteLLMProvider(model_default="ollama/qwen2.5:0.5b", api_base="http://127.0.0.1:11434")
    _ = provider.chat("test prompt")

    # Assert: global unchanged + per-request kw used
    assert getattr(litellm, "api_base", None) == "SHOULD_NOT_CHANGE"
    assert calls["kwargs"].get("api_base") == "http://127.0.0.1:11434"

    # Cleanup
    monkeypatch.setattr(litellm, "api_base", orig, raising=False)


def test_provider_with_empty_api_base_uses_none(monkeypatch):
    """Provider should normalize empty string api_base to None."""
    calls = {}

    def fake_completion(*args, **kwargs):
        calls["kwargs"] = kwargs
        return {"choices": [{"message": {"content": "ok"}}], "model": "test", "usage": {}}

    monkeypatch.setattr(litellm, "completion", fake_completion)

    # Test empty string normalization
    provider = LiteLLMProvider(model_default="openai/gpt-4o-mini", api_base="")
    _ = provider.chat("test")

    # Should not include api_base in kwargs when empty
    assert "api_base" not in calls["kwargs"]


def test_mix_ollama_then_openai_isolated(monkeypatch):
    """Test that Ollama -> OpenAI calls don't contaminate each other."""
    seen_api_bases = []

    def fake_completion(*args, **kwargs):
        seen_api_bases.append(kwargs.get("api_base"))
        return {"choices": [{"message": {"content": "ok"}}], "model": "test", "usage": {}}

    monkeypatch.setattr(litellm, "completion", fake_completion)

    # First call with Ollama (has api_base)
    ollama_provider = LiteLLMProvider(model_default="ollama/qwen2.5:0.5b", api_base="http://127.0.0.1:11434")
    ollama_provider.chat("test ollama")

    # Second call with OpenAI (no api_base)
    openai_provider = LiteLLMProvider(model_default="openai/gpt-4o-mini")
    openai_provider.chat("test openai")

    # Assert: Ollama used custom base, OpenAI used default (None)
    assert seen_api_bases == ["http://127.0.0.1:11434", None]


def test_streaming_also_uses_per_request_isolation(monkeypatch):
    """Test that streaming calls also pass api_base per-request."""
    calls = {}

    # Create mock objects that match the expected structure
    class MockDelta:
        def __init__(self, content):
            self.content = content

    class MockChoice:
        def __init__(self, content):
            self.delta = MockDelta(content)

    class MockChunk:
        def __init__(self, content):
            self.choices = [MockChoice(content)]

    def fake_completion(*args, **kwargs):
        calls["kwargs"] = kwargs
        # Mock streaming response with proper structure
        return [
            MockChunk("chunk1"),
            MockChunk("chunk2"),
        ]

    monkeypatch.setattr(litellm, "completion", fake_completion)

    provider = LiteLLMProvider(model_default="ollama/qwen2.5:0.5b", api_base="http://127.0.0.1:11434")

    # Consume the stream
    chunks = list(provider.stream_chat("test streaming"))

    # Verify api_base was passed per-request
    assert calls["kwargs"].get("api_base") == "http://127.0.0.1:11434"
    assert calls["kwargs"].get("stream") is True
    assert chunks == ["chunk1", "chunk2"]
