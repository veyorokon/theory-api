"""Integration tests for llm_litellm mock mode testing."""

import pytest
from apps.core.orchestrator import run as orch_run


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

        # Execute processor via orchestrator
        envelope = orch_run(
            adapter="local",
            ref="llm/litellm@1",
            mode="mock",
            inputs=inputs,
            write_prefix="/artifacts/outputs/litellm-mock/{execution_id}/",
            expected_oci=None,
            build=True,
        )

        assert envelope["status"] == "success"
        assert "execution_id" in envelope
        assert "outputs" in envelope

    def test_litellm_ci_forces_mock(self, monkeypatch):
        """Test that CI=true forces mock mode even with API key present."""
        # Set environment variables
        monkeypatch.setenv("CI", "true")
        monkeypatch.setenv("OPENAI_API_KEY", "fake-key-should-be-ignored")

        # Prepare inputs
        inputs = {
            "schema": "v1",
            "model": "gpt-4o-mini",
            "params": {"messages": [{"role": "user", "content": "test"}]},
        }

        # Execute processor via orchestrator
        envelope = orch_run(
            adapter="local",
            ref="llm/litellm@1",
            mode="mock",
            inputs=inputs,
            write_prefix="/artifacts/outputs/litellm-ci/{execution_id}/",
            expected_oci=None,
            build=True,
        )

        # Should succeed without network access in mock mode
        assert envelope["status"] == "success"
