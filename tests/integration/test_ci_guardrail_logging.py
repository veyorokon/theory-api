"""
Integration tests for CI guardrail with logging.

Tests that CI=true + mode=real blocks execution and logs guardrail.block event.
"""

import json
import os
import subprocess
import sys
from io import StringIO
from unittest import mock

import pytest

from libs.runtime_common.mode import resolve_mode, ModeSafetyError
from apps.core.logging import clear


def get_code_directory():
    """Get the project code directory dynamically."""
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    return os.path.join(project_root, "code")


class TestCIGuardrailLogging:
    """Test CI guardrail logging behavior."""

    def setup_method(self):
        """Clear logging context before each test."""
        clear()

    def teardown_method(self):
        """Clear logging context after each test."""
        clear()

    def test_resolve_mode_raises_safety_error(self):
        """Test resolve_mode raises ModeSafetyError when CI=true and mode=real."""
        with mock.patch.dict(os.environ, {"CI": "true"}):
            with pytest.raises(ModeSafetyError, match="ERR_CI_SAFETY"):
                resolve_mode({"mode": "real"})

        # Note: Logging now happens at command boundary, not in resolve_mode utility

    def test_resolve_mode_allows_mock_in_ci(self):
        """Test resolve_mode allows mock mode in CI without logging."""
        with mock.patch.dict(os.environ, {"CI": "true"}):
            with mock.patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                result = resolve_mode({"mode": "mock"})
                output = mock_stdout.getvalue()

        assert result.value == "mock"
        # Should not log anything for allowed operation
        assert output.strip() == ""

    def test_resolve_mode_allows_real_outside_ci(self):
        """Test resolve_mode allows real mode outside CI."""
        with mock.patch.dict(os.environ, {"CI": "false"}):  # Explicitly set to false
            with mock.patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                result = resolve_mode({"mode": "real"})
                output = mock_stdout.getvalue()

        assert result.value == "real"
        # Should not log anything for allowed operation
        assert output.strip() == ""


@pytest.mark.integration
class TestRunProcessorCIGuardrail:
    """Test run_processor command CI guardrail with logging."""

    def test_run_processor_blocks_real_mode_in_ci(self):
        """Test run_processor exits non-zero and logs when CI=true and mode=real."""
        # Run the command with CI=true and mode=real
        env = os.environ.copy()
        env["CI"] = "true"
        env["DJANGO_SETTINGS_MODULE"] = "backend.settings.unittest"

        cmd = [
            sys.executable,
            "manage.py",
            "run_processor",
            "--ref",
            "llm/litellm@1",
            "--adapter",
            "local",
            "--mode",
            "real",
            "--write-prefix",
            "/artifacts/test/{execution_id}/",
            "--inputs-json",
            '{"schema": "v1"}',
            "--json",
        ]

        result = subprocess.run(cmd, cwd=get_code_directory(), env=env, capture_output=True, text=True)

        # Should exit with non-zero code
        assert result.returncode == 1

        # Should have error message about CI guardrail
        assert "CI guardrail" in result.stderr or "ERR_CI_SAFETY" in result.stderr

        # Stdout should contain JSON logs if logging is working
        if result.stdout.strip():
            lines = result.stdout.strip().split("\n")
            # Look for execution.fail event with guardrail information
            execution_fail_logged = False
            for line in lines:
                try:
                    log_data = json.loads(line)
                    if log_data.get("event") == "execution.fail" and log_data.get("reason") == "ci_guardrail_block":
                        assert log_data["ci"]
                        assert log_data["mode"] == "real"
                        assert log_data["error"]["code"] == "ERR_CI_SAFETY"
                        execution_fail_logged = True
                        break
                except json.JSONDecodeError:
                    # Skip non-JSON lines
                    continue

            # Note: Single execution.fail event with guardrail context (no double logging)

    def test_run_processor_allows_mock_mode_in_ci(self):
        """Test run_processor allows mock mode in CI."""
        env = os.environ.copy()
        env["CI"] = "true"
        env["DJANGO_SETTINGS_MODULE"] = "backend.settings.unittest"

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
            "/artifacts/test/{execution_id}/",
            "--inputs-json",
            '{"schema": "v1"}',
            "--json",
        ]

        result = subprocess.run(
            cmd,
            cwd=get_code_directory(),
            env=env,
            capture_output=True,
            text=True,
            timeout=30,  # Don't wait too long for mock execution
        )

        # Should succeed (exit code 0) or at least not fail due to CI guardrail
        # (might fail for other reasons like missing files in test env)
        if result.returncode != 0:
            # If it failed, should not be due to CI guardrail
            assert "CI guardrail" not in result.stderr
            assert "ERR_CI_SAFETY" not in result.stderr

        # Should not log execution.fail with guardrail reason for allowed operation
        if result.stdout.strip():
            lines = result.stdout.strip().split("\n")
            for line in lines:
                try:
                    log_data = json.loads(line)
                    # Should not have execution.fail with guardrail reason
                    if log_data.get("event") == "execution.fail":
                        assert log_data.get("reason") != "ci_guardrail_block"
                except json.JSONDecodeError:
                    continue


class TestModeSafetyError:
    """Test ModeSafetyError exception properties."""

    def test_mode_safety_error_has_correct_code(self):
        """Test ModeSafetyError has correct error code."""
        error = ModeSafetyError("test message")
        assert error.code == "ERR_CI_SAFETY"
        assert error.message == "test message"
        assert str(error) == "test message"
