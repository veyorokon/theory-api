"""Integration tests for Modal app functionality."""

import json
import os
import tarfile
import tempfile
import pytest
from unittest.mock import patch, MagicMock, mock_open
from django.test import SimpleTestCase


pytestmark = pytest.mark.integration


class TestModalApp:
    def setup_method(self):
        self.test_payload = {
            "inputs_json": {"messages": [{"role": "user", "content": "test"}]},
            "write_prefix": "/artifacts/test/",
        }

    @pytest.mark.skip("Modal app module requires environment setup - integration test required")
    @patch.dict(
        os.environ, {"PROCESSOR_REF": "test/proc@1", "IMAGE_REF": "test@sha256:abc123", "MODAL_ENVIRONMENT": "dev"}
    )
    @patch("subprocess.run")
    @patch("os.makedirs")
    @patch("builtins.open", new_callable=mock_open)
    @patch("json.dump")
    def test_inputs_json_written(self, mock_json_dump, mock_file, mock_makedirs, mock_subprocess):
        """Test inputs.json is written correctly before execution"""
        from modal_app import run

        # Mock successful subprocess execution
        mock_subprocess.return_value = MagicMock(returncode=0)

        # Mock os.walk to return empty (no output files)
        with patch("os.walk", return_value=[]):
            with patch("tarfile.open"):
                result = run(self.test_payload)

        # Verify inputs.json was written with correct content
        mock_makedirs.assert_called_with("/work", exist_ok=True)
        mock_json_dump.assert_called_with(
            self.test_payload["inputs_json"],
            mock_file.return_value.__enter__.return_value,
            ensure_ascii=False,
            separators=(",", ":"),
        )

    @pytest.mark.skip("Modal app module requires environment setup - integration test required")
    @patch.dict(os.environ, {"PROCESSOR_REF": "test/proc@1", "IMAGE_REF": "test@sha256:abc123"})
    @patch("subprocess.run")
    def test_processor_failure_with_stderr(self, mock_subprocess):
        """Test modal_app.run handles subprocess failure with stderr tail"""
        from modal_app import run
        from subprocess import CalledProcessError

        # Mock subprocess failure with stderr
        mock_subprocess.side_effect = CalledProcessError(
            returncode=1, cmd=["python", "/app/main.py"], stderr="Error line 1\nError line 2\nFatal error occurred"
        )

        with pytest.raises(RuntimeError) as exc_info:
            run(self.test_payload)

        # Verify error message includes stderr tail
        error_msg = str(exc_info.value)
        assert "processor failed (exit=1)" in error_msg
        assert "Fatal error occurred" in error_msg

    @pytest.mark.skip("Modal app module requires environment setup - integration test required")
    def test_app_name_generation(self):
        """Test Modal app name generation from environment"""
        with patch.dict(os.environ, {"PROCESSOR_REF": "llm/litellm@1", "MODAL_ENVIRONMENT": "dev"}):
            from modal_app import _modal_app_name_from_env

            app_name = _modal_app_name_from_env()
            assert "llm-litellm-v1-dev" in app_name
