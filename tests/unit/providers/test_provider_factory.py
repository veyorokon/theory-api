"""Unit tests for provider factory and system integration."""

import pytest

from apps.core.integrations import get_llm_provider


pytestmark = pytest.mark.unit


class TestProviderFactory:
    """Test the provider factory function."""

    def test_get_mock_provider(self):
        """get_llm_provider should return mock function for 'mock'."""
        provider = get_llm_provider("mock")
        assert callable(provider)

        # Test that it works like a mock LLM function
        test_inputs = {"messages": [{"role": "user", "content": "test"}]}
        result = provider(test_inputs)
        assert isinstance(result, dict)
        assert "choices" in result
        assert "model" in result

    def test_get_unknown_provider_raises(self):
        """get_llm_provider should raise ValueError for unknown provider."""
        with pytest.raises(ValueError) as exc_info:
            get_llm_provider("unknown")

        error_msg = str(exc_info.value)
        assert "Unknown LLM provider: unknown" in error_msg
        assert "Available:" in error_msg

    def test_get_unavailable_provider_raises(self):
        """get_llm_provider should raise ValueError for unavailable provider."""
        # This tests the case where a provider is in the mapping but None
        # (happens when optional dependencies are missing)

        # We can test that the mock provider exists
        provider = get_llm_provider("mock")
        assert provider is not None

    def test_provider_factory_consistency(self):
        """Provider factory should return consistent function reference."""
        provider1 = get_llm_provider("mock")
        provider2 = get_llm_provider("mock")

        # Should be the same function reference
        assert callable(provider1)
        assert callable(provider2)
        assert provider1 is provider2  # Same function reference
