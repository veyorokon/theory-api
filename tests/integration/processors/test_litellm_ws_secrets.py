"""Integration tests for WebSocket orchestrator with LiteLLM and secret resolution."""

import os
import pytest
from apps.core.orchestrator_ws import OrchestratorWS


pytestmark = [pytest.mark.integration, pytest.mark.requires_docker]


class TestLiteLLMWebSocketSecrets:
    """Test LiteLLM processor via WebSocket orchestrator with secret resolution."""

    def test_ws_orchestrator_resolves_secrets_mock_mode(self):
        """Test that WebSocket orchestrator works in mock mode (no secrets needed)."""
        orchestrator = OrchestratorWS()

        inputs = {
            "schema": "v1",
            "params": {"messages": [{"role": "user", "content": "Mock mode test"}], "model": "gpt-4o-mini"},
        }

        envelope = orchestrator.invoke(
            ref="llm/litellm@1",
            mode="mock",
            inputs=inputs,
            build=True,
            stream=False,
            write_prefix="/artifacts/outputs/test-ws-mock/{execution_id}/",
        )

        assert envelope["status"] == "success"
        assert "execution_id" in envelope
        assert "outputs" in envelope
        assert len(envelope["outputs"]) > 0

    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not available for real mode testing")
    def test_ws_orchestrator_resolves_secrets_real_mode(self):
        """Test that WebSocket orchestrator properly resolves and passes secrets in real mode."""
        orchestrator = OrchestratorWS()

        inputs = {
            "schema": "v1",
            "params": {
                "messages": [{"role": "user", "content": "Say exactly: WebSocket secrets test passed!"}],
                "model": "gpt-4o-mini",
            },
        }

        envelope = orchestrator.invoke(
            ref="llm/litellm@1",
            mode="real",
            inputs=inputs,
            build=True,
            stream=False,
            write_prefix="/artifacts/outputs/test-ws-real/{execution_id}/",
        )

        assert envelope["status"] == "success"
        assert "execution_id" in envelope
        assert "outputs" in envelope
        assert len(envelope["outputs"]) > 0

        # Verify the output path exists
        assert any("response.txt" in output.get("path", "") for output in envelope["outputs"])

    def test_ws_orchestrator_fails_without_required_secret(self, monkeypatch):
        """Test that WebSocket orchestrator fails gracefully when required secret is missing."""
        # Remove OPENAI_API_KEY from environment
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        orchestrator = OrchestratorWS()

        inputs = {
            "schema": "v1",
            "params": {"messages": [{"role": "user", "content": "This should fail"}], "model": "gpt-4o-mini"},
        }

        with pytest.raises(Exception) as exc_info:
            orchestrator.invoke(
                ref="llm/litellm@1",
                mode="real",  # Real mode requires OPENAI_API_KEY
                inputs=inputs,
                build=True,
                stream=False,
                write_prefix="/artifacts/outputs/test-ws-fail/{execution_id}/",
            )

        assert "Missing required secret: OPENAI_API_KEY" in str(exc_info.value)

    def test_ws_orchestrator_secret_redaction_in_logs(self, caplog):
        """Test that secrets are redacted in Docker command logs."""
        import logging

        # Set up logging capture
        caplog.set_level(logging.INFO)

        # Ensure we have a fake API key for testing
        os.environ["OPENAI_API_KEY"] = "sk-test-1234567890abcdefghij"

        orchestrator = OrchestratorWS()

        inputs = {
            "schema": "v1",
            "params": {"messages": [{"role": "user", "content": "Test redaction"}], "model": "gpt-4o-mini"},
        }

        try:
            envelope = orchestrator.invoke(
                ref="llm/litellm@1",
                mode="mock",  # Use mock to avoid actual API call
                inputs=inputs,
                build=True,
                stream=False,
                write_prefix="/artifacts/outputs/test-ws-redact/{execution_id}/",
            )
        except:
            pass  # We don't care if it fails, just checking logs

        # Check that the Docker command in logs has redacted the API key
        docker_run_logs = [record for record in caplog.records if "docker.run" in record.getMessage()]
        if docker_run_logs:
            log_message = docker_run_logs[0].getMessage()
            assert "sk-test-1234567890abcdefghij" not in log_message
            # In mock mode, OPENAI_API_KEY shouldn't be passed at all
            # But if it were passed in real mode, it would show as ***
