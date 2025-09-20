"""Integration test for CI safety guardrail in run_processor command."""

import json
import os
import subprocess
import pytest


pytestmark = pytest.mark.integration


class TestCISafety:
    """Test CI safety guardrail in actual command execution."""

    def test_ci_blocks_real_mode_command(self):
        """Test that run_processor fails when CI=true and mode=real."""
        cmd = [
            "python",
            "manage.py",
            "run_processor",
            "--ref",
            "llm/litellm@1",
            "--adapter",
            "local",
            "--mode",
            "real",
            "--write-prefix",
            "/artifacts/outputs/ci-test/{execution_id}/",
            "--inputs-json",
            '{"schema":"v1","params":{"messages":[{"role":"user","content":"test"}]}}',
            "--json",
        ]

        env = os.environ.copy()
        env["CI"] = "true"
        env["PYTHONPATH"] = "."

        result = subprocess.run(cmd, cwd=".", env=env, capture_output=True, text=True)

        # Should fail with non-zero exit code
        assert result.returncode != 0, "Expected command to fail in CI with mode=real"

        # Try to parse JSON error response
        try:
            payload = json.loads(result.stdout)
            assert payload.get("status") == "error"
            assert "ERR_CI_SAFETY" in payload.get("error", {}).get("code", "")
        except json.JSONDecodeError:
            # If no JSON, error should be in stderr
            assert "Real mode is blocked in CI" in result.stderr or "ERR_CI_SAFETY" in result.stderr

    def test_ci_allows_mock_mode_command(self):
        """Test that run_processor succeeds when CI=true and mode=mock."""
        cmd = [
            "python",
            "manage.py",
            "run_processor",
            "--ref",
            "llm/litellm@1",
            "--adapter",
            "local",
            "--mode",
            "mock",
            "--write-prefix",
            "/artifacts/outputs/ci-mock-test/{execution_id}/",
            "--inputs-json",
            '{"schema":"v1","params":{"messages":[{"role":"user","content":"test"}]}}',
            "--json",
        ]

        env = os.environ.copy()
        env["CI"] = "true"
        env["PYTHONPATH"] = "."

        result = subprocess.run(cmd, cwd=".", env=env, capture_output=True, text=True)

        # Should succeed (CI guardrail passes, Docker issues are acceptable)
        assert result.returncode == 0, f"Command should succeed in CI with mode=mock: {result.stderr}"

        # Parse JSON response - may be error due to Docker but not CI guardrail
        payload = json.loads(result.stdout)
        # Success means actual execution, error means Docker/container issue but CI guardrail passed
        assert payload["status"] in ["success", "error"]
        if payload["status"] == "error":
            # Verify it's not a CI safety error
            assert "ERR_CI_SAFETY" not in payload.get("error", {}).get("code", "")

    def test_ci_defaults_to_mock_when_no_mode(self):
        """Test that CI=true defaults to mock mode when no mode specified."""
        cmd = [
            "python",
            "manage.py",
            "run_processor",
            "--ref",
            "llm/litellm@1",
            "--adapter",
            "local",
            "--write-prefix",
            "/artifacts/outputs/ci-default-test/{execution_id}/",
            "--inputs-json",
            '{"schema":"v1","params":{"messages":[{"role":"user","content":"test"}]}}',
            "--json",
        ]

        env = os.environ.copy()
        env["CI"] = "true"
        env["PYTHONPATH"] = "."

        result = subprocess.run(cmd, cwd=".", env=env, capture_output=True, text=True)

        # Should succeed with mock mode (CI guardrail passes, Docker issues acceptable)
        assert result.returncode == 0, f"Command should succeed with CI default: {result.stderr}"

        payload = json.loads(result.stdout)
        # Success means actual execution, error means Docker/container issue but CI guardrail passed
        assert payload["status"] in ["success", "error"]
        if payload["status"] == "error":
            # Verify it's not a CI safety error
            assert "ERR_CI_SAFETY" not in payload.get("error", {}).get("code", "")
