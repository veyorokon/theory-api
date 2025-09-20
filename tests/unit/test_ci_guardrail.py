"""Test CI safety guardrail for mode system."""

import os
import pytest
from unittest.mock import patch

from libs.runtime_common.mode import resolve_mode, ModeError


class TestCIGuardrail:
    """Test CI environment safety guardrail."""

    def test_ci_blocks_real_mode(self):
        """Test that CI=true blocks mode=real."""
        inputs = {"mode": "real"}

        with patch.dict(os.environ, {"CI": "true"}, clear=True):
            with pytest.raises(ModeError) as exc_info:
                resolve_mode(inputs)

            assert exc_info.value.code == "ERR_CI_SAFETY"
            assert "Real mode is blocked in CI" in str(exc_info.value)

    def test_ci_allows_mock_mode(self):
        """Test that CI=true allows mode=mock."""
        inputs = {"mode": "mock"}

        with patch.dict(os.environ, {"CI": "true"}, clear=True):
            mode = resolve_mode(inputs)
            assert mode == "mock"

    def test_ci_allows_smoke_mode(self):
        """Test that CI=true allows mode=smoke."""
        inputs = {"mode": "smoke"}

        with patch.dict(os.environ, {"CI": "true"}, clear=True):
            mode = resolve_mode(inputs)
            assert mode == "smoke"

    def test_non_ci_allows_real_mode(self):
        """Test that non-CI environment allows mode=real."""
        inputs = {"mode": "real"}

        with patch.dict(os.environ, {}, clear=True):
            mode = resolve_mode(inputs)
            assert mode == "real"

    def test_ci_false_allows_real_mode(self):
        """Test that CI=false allows mode=real."""
        inputs = {"mode": "real"}

        with patch.dict(os.environ, {"CI": "false"}, clear=True):
            mode = resolve_mode(inputs)
            assert mode == "real"

    def test_default_mode_in_ci(self):
        """Test that default mode (mock) works in CI."""
        inputs = {}  # No mode specified

        with patch.dict(os.environ, {"CI": "true"}, clear=True):
            mode = resolve_mode(inputs)
            assert mode == "mock"  # Default is mock, which is allowed in CI
