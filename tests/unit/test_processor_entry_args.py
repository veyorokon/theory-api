"""Test processor entry point argument parity."""

import subprocess
import pytest


class TestProcessorEntryArgs:
    """Test that all processors accept standard CLI arguments."""

    @pytest.mark.parametrize(
        "processor_image",
        [
            "theory-local-build:dev",  # LiteLLM processor built locally
        ],
    )
    def test_processor_help_flag(self, processor_image):
        """Test that processor containers accept --help flag."""
        result = subprocess.run(
            ["docker", "run", "--rm", processor_image, "--help"], capture_output=True, text=True, timeout=10
        )

        # Should succeed and show usage information
        assert result.returncode == 0
        assert "--inputs" in result.stdout
        assert "--write-prefix" in result.stdout
        assert "--execution-id" in result.stdout

    @pytest.mark.parametrize(
        "processor_image",
        [
            "theory-local-build:dev",  # LiteLLM processor built locally
        ],
    )
    def test_processor_required_args(self, processor_image):
        """Test that processor containers require standard arguments."""
        # Missing all required args should fail
        result = subprocess.run(["docker", "run", "--rm", processor_image], capture_output=True, text=True, timeout=10)

        assert result.returncode != 0
        assert "required" in result.stderr.lower()

    def test_entry_args_consistency(self):
        """Test that all processors have consistent argument interfaces."""
        processors = ["theory-local-build:dev"]

        arg_patterns = []
        for processor in processors:
            result = subprocess.run(
                ["docker", "run", "--rm", processor, "--help"], capture_output=True, text=True, timeout=10
            )

            if result.returncode == 0:
                # Extract argument patterns
                required_args = set()
                if "--inputs" in result.stdout:
                    required_args.add("inputs")
                if "--write-prefix" in result.stdout:
                    required_args.add("write-prefix")
                if "--execution-id" in result.stdout:
                    required_args.add("execution-id")

                arg_patterns.append(required_args)

        # All processors should have identical argument patterns
        if arg_patterns:
            first_pattern = arg_patterns[0]
            for pattern in arg_patterns[1:]:
                assert pattern == first_pattern, "Processor argument interfaces are not consistent"
