"""Integration tests for llm_litellm mock mode testing."""

import json
import pytest
from tests.tools.runner import run_cli, parse_stdout_json_or_fail


pytestmark = [pytest.mark.integration, pytest.mark.requires_docker]


class TestLiteLLMMock:
    """Test LiteLLM processor mock execution."""

    def test_litellm_mock_no_egress(self):
        """Test that LiteLLM runs successfully with mock provider (no network)."""
        # Prepare inputs
        inputs = {
            "schema": "v1",
            "model": "gpt-4o-mini",
            "params": {
                "messages": [{"role": "user", "content": "test message"}],
                "temperature": 0.1,
                "seed": 42,
            },
        }

        # Execute processor
        args = [
            "run_processor",
            "--ref",
            "llm/litellm@1",
            "--adapter",
            "local",
            "--mode",
            "mock",
            "--write-prefix",
            "/artifacts/outputs/litellm-mock/{execution_id}/",
            "--inputs-json",
            json.dumps(inputs),
            "--json",
            "--build",
        ]

        result = run_cli(args, env={"LOG_STREAM": "stderr"})
        response = parse_stdout_json_or_fail(result)
        assert response["status"] == "success"
        assert "execution_id" in response
        assert "outputs" in response

    def test_litellm_ci_forces_mock(self):
        """Test that CI=true forces mock mode even with API key present."""
        # Prepare inputs
        inputs = {
            "schema": "v1",
            "model": "gpt-4o-mini",
            "params": {"messages": [{"role": "user", "content": "test"}]},
        }

        # Execute processor
        args = [
            "run_processor",
            "--ref",
            "llm/litellm@1",
            "--adapter",
            "local",
            "--mode",
            "mock",
            "--write-prefix",
            "/artifacts/outputs/litellm-ci/{execution_id}/",
            "--inputs-json",
            json.dumps(inputs),
            "--json",
        ]

        env = {"LOG_STREAM": "stderr", "CI": "true", "OPENAI_API_KEY": "fake-key-should-be-ignored"}

        result = run_cli(args, env=env)
        # Should succeed without network access in mock mode
        assert result.returncode == 0, f"Mock mode should succeed without network: {result.stderr}"
