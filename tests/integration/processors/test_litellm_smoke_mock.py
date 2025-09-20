"""Integration tests for llm_litellm smoke testing with mock."""

import json
import subprocess
import sys
import os
import tempfile
from pathlib import Path

import pytest


pytestmark = pytest.mark.integration


class TestLiteLLMSmokeMock:
    """Test LiteLLM processor smoke execution with mock runner."""

    def test_litellm_smoke_mock_no_egress(self):
        """Test that LiteLLM runs successfully with mock provider (no network)."""
        # Prepare inputs
        inputs = {
            "messages": [{"role": "user", "content": "test message"}],
            "model": "gpt-4o-mini",
            "temperature": 0.1,
            "seed": 42,
        }

        # Execute processor
        cmd = [
            sys.executable,
            "manage.py",
            "run_processor",
            "--ref",
            "llm/litellm@1",
            "--adapter",
            "local",
            "--mode",
            "smoke",
            "--write-prefix",
            "/artifacts/outputs/litellm-smoke/{execution_id}/",
            "--inputs-json",
            json.dumps(inputs),
            "--json",
        ]

        env = os.environ.copy()
        env["LLM_PROVIDER"] = "mock"
        env["PYTHONPATH"] = "."

        result = subprocess.run(cmd, env=env, capture_output=True, text=True, cwd=".")

        # Verify success
        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # Parse response
        response = json.loads(result.stdout)
        assert response["status"] == "success"
        assert "execution_id" in response
        assert "outputs" in response

    def test_litellm_ci_forces_mock(self):
        """Test that CI=true forces mock mode even with API key present."""
        # Prepare inputs
        inputs = {"messages": [{"role": "user", "content": "test"}], "model": "gpt-4o-mini"}

        # Execute processor
        cmd = [
            sys.executable,
            "manage.py",
            "run_processor",
            "--ref",
            "llm/litellm@1",
            "--adapter",
            "local",
            "--mode",
            "smoke",
            "--write-prefix",
            "/artifacts/outputs/litellm-ci/{execution_id}/",
            "--inputs-json",
            json.dumps(inputs),
            "--json",
        ]

        env = os.environ.copy()
        env["LLM_PROVIDER"] = "mock"
        env["PYTHONPATH"] = "."
        env["CI"] = "true"
        env["OPENAI_API_KEY"] = "fake-key-should-be-ignored"

        result = subprocess.run(cmd, env=env, capture_output=True, text=True, cwd=".")

        # Should succeed without network access
        assert result.returncode == 0, f"CI mode should force mock: {result.stderr}"
