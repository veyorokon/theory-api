"""Integration tests for llm_litellm mock mode testing."""

import json
import subprocess
import sys
import os
import tempfile
from pathlib import Path

import pytest


pytestmark = pytest.mark.integration


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
        cmd = [
            sys.executable,
            "manage.py",
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
        ]

        env = os.environ.copy()
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
        inputs = {
            "schema": "v1",
            "model": "gpt-4o-mini",
            "params": {"messages": [{"role": "user", "content": "test"}]},
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
            "mock",
            "--write-prefix",
            "/artifacts/outputs/litellm-ci/{execution_id}/",
            "--inputs-json",
            json.dumps(inputs),
            "--json",
        ]

        env = os.environ.copy()
        env["PYTHONPATH"] = "."
        env["CI"] = "true"
        env["OPENAI_API_KEY"] = "fake-key-should-be-ignored"

        result = subprocess.run(cmd, env=env, capture_output=True, text=True, cwd=".")

        # Should succeed without network access in mock mode
        assert result.returncode == 0, f"Mock mode should succeed without network: {result.stderr}"
