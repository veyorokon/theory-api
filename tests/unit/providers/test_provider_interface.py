"""Contract tests for universal provider interface."""

import inspect
import pytest
import sys
from pathlib import Path

# Add processor paths to import from containers
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "code" / "apps" / "core" / "processors"))

from apps.core.integrations.types import ProviderRunner
from apps.core.processors.replicate_generic.provider import ProcessorResult
from libs.runtime_common.processor import ProviderConfig


pytestmark = pytest.mark.unit


def _is_callable_runner(obj):
    """Check if object is a callable matching ProviderRunner protocol."""
    return callable(obj) and len(inspect.signature(obj).parameters) == 1


class TestProviderInterface:
    """Test that all providers conform to the universal make_runner interface."""

    def test_all_providers_export_make_runner(self):
        """All providers must export make_runner(config) -> callable."""
        # Import from processor containers
        from llm_litellm.provider import make_runner as make_litellm_runner
        from replicate_generic.provider import make_runner as make_replicate_runner

        # Test both providers export make_runner
        for make_runner_func, name in [(make_litellm_runner, "litellm"), (make_replicate_runner, "replicate")]:
            # Test with mock config
            config = ProviderConfig(mock=True)
            runner = make_runner_func(config)

            assert _is_callable_runner(runner), f"{name} make_runner must return callable(inputs)->ProcessorResult"

    def test_provider_runners_return_processor_result(self):
        """All provider runners must return ProcessorResult instances."""
        from llm_litellm.provider import make_runner as make_litellm_runner
        from replicate_generic.provider import make_runner as make_replicate_runner

        # Test LiteLLM with v1 inputs
        config = ProviderConfig(mock=True)
        llm_runner = make_litellm_runner(config)
        llm_result = llm_runner({"schema": "v1", "params": {"messages": [{"role": "user", "content": "test"}]}})
        assert isinstance(llm_result, ProcessorResult), "LiteLLM runner must return ProcessorResult"

        # Test Replicate with v1 inputs
        rep_runner = make_replicate_runner(config)
        rep_result = rep_runner({"schema": "v1", "model": "test/model@1", "params": {"prompt": "test"}})
        assert isinstance(rep_result, ProcessorResult), "Replicate runner must return ProcessorResult"

    def test_processor_result_has_required_fields(self):
        """ProcessorResult must have all required fields for universal pattern."""
        from llm_litellm.provider import make_runner as make_litellm_runner

        config = ProviderConfig(mock=True)
        runner = make_litellm_runner(config)
        result = runner({"schema": "v1", "params": {"messages": [{"role": "user", "content": "test"}]}})

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
        from llm_litellm.provider import make_runner as make_litellm_runner

        config = ProviderConfig(mock=True)
        runner = make_litellm_runner(config)
        result = runner({"schema": "v1", "params": {"messages": [{"role": "user", "content": "test"}]}})

        for output in result.outputs:
            assert output.relpath.startswith("outputs/"), (
                f"OutputItem relpath must start with 'outputs/', got: {output.relpath}"
            )

    def test_v1_inputs_normalization(self):
        """Test that legacy inputs are normalized to v1 schema."""
        from libs.runtime_common.processor import validate_and_normalize_v1

        # Test LiteLLM legacy format
        legacy_llm = {"messages": [{"role": "user", "content": "test"}], "model": "gpt-4"}
        normalized = validate_and_normalize_v1(legacy_llm)
        assert normalized["schema"] == "v1"
        assert normalized["model"] == "gpt-4"
        assert normalized["params"]["messages"] == legacy_llm["messages"]

        # Test Replicate legacy format
        legacy_rep = {"model": "test/model", "input": {"prompt": "test"}}
        normalized = validate_and_normalize_v1(legacy_rep)
        assert normalized["schema"] == "v1"
        assert normalized["model"] == "test/model"
        assert normalized["params"] == {"prompt": "test"}
