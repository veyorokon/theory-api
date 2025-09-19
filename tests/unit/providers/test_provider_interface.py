"""Contract tests for universal provider interface."""

import inspect
import pytest

from apps.core.integrations import litellm_provider, replicate_provider
from apps.core.integrations.types import ProviderRunner, ProcessorResult


pytestmark = pytest.mark.unit


def _is_callable_runner(obj):
    """Check if object is a callable matching ProviderRunner protocol."""
    return callable(obj) and len(inspect.signature(obj).parameters) == 1


class TestProviderInterface:
    """Test that all providers conform to the universal ProviderRunner interface."""

    def test_all_providers_return_callable_runners(self):
        """All providers must return callable runners matching ProviderRunner protocol."""
        providers = [
            litellm_provider,
            replicate_provider,
        ]

        for provider_module in providers:
            # Test with CI mode (mock)
            runner = (
                provider_module.select_litellm_runner(ci=True, token_or_key="")
                if hasattr(provider_module, "select_litellm_runner")
                else provider_module.select_replicate_runner(ci=True, token_or_key="")
            )

            assert _is_callable_runner(runner), (
                f"{provider_module.__name__} must return callable(inputs)->ProcessorResult"
            )

    def test_provider_runners_return_processor_result(self):
        """All provider runners must return ProcessorResult instances."""
        # Test LiteLLM
        llm_runner = litellm_provider.select_litellm_runner(ci=True, token_or_key="")
        llm_result = llm_runner({"messages": [{"role": "user", "content": "test"}]})
        assert isinstance(llm_result, ProcessorResult), "LiteLLM runner must return ProcessorResult"

        # Test Replicate
        rep_runner = replicate_provider.select_replicate_runner(ci=True, token_or_key="")
        rep_result = rep_runner({"model": "test/model@1", "params": {"prompt": "test"}})
        assert isinstance(rep_result, ProcessorResult), "Replicate runner must return ProcessorResult"

    def test_processor_result_has_required_fields(self):
        """ProcessorResult must have all required fields for universal pattern."""
        runner = litellm_provider.select_litellm_runner(ci=True, token_or_key="")
        result = runner({"messages": [{"role": "user", "content": "test"}]})

        # Check required fields
        assert hasattr(result, "outputs"), "ProcessorResult must have outputs field"
        assert hasattr(result, "processor_info"), "ProcessorResult must have processor_info field"
        assert hasattr(result, "usage"), "ProcessorResult must have usage field"
        assert hasattr(result, "extra"), "ProcessorResult must have extra field"

        # Check types
        assert isinstance(result.outputs, list), "outputs must be a list"
        assert isinstance(result.processor_info, str), "processor_info must be a string"
        assert isinstance(result.usage, dict), "usage must be a dict"
        assert isinstance(result.extra, dict), "extra must be a dict"

    def test_output_items_have_outputs_prefix(self):
        """All OutputItems must have relpath starting with 'outputs/'."""
        runner = litellm_provider.select_litellm_runner(ci=True, token_or_key="")
        result = runner({"messages": [{"role": "user", "content": "test"}]})

        for output in result.outputs:
            assert output.relpath.startswith("outputs/"), (
                f"OutputItem relpath must start with 'outputs/', got: {output.relpath}"
            )
