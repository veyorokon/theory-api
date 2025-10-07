"""Test clean mode system validation."""

import os
from unittest import mock

import pytest

from libs.runtime_common.envelope import resolve_mode, is_mock, is_real, ModeSafetyError


class TestModeSystem:
    """Test the clean two-mode system."""

    def test_mock_mode_validation(self):
        """Test that mock mode is parsed correctly."""
        inputs = {"mode": "mock"}
        mode = resolve_mode(inputs)
        assert mode.value == "mock"
        assert is_mock(mode)
        assert not is_real(mode)

    @mock.patch.dict(os.environ, {"CI": ""}, clear=True)
    def test_real_mode_validation(self):
        """Test that real mode is parsed correctly when not in CI."""
        inputs = {"mode": "real"}
        mode = resolve_mode(inputs)
        assert mode.value == "real"
        assert is_real(mode)
        assert not is_mock(mode)

    def test_invalid_mode_rejection(self):
        """Test that invalid modes are rejected."""
        inputs = {"mode": "smoke"}
        with pytest.raises(ValueError) as exc_info:
            resolve_mode(inputs)
        assert "Invalid mode 'smoke'" in str(exc_info.value)
        assert "Allowed: ['mock', 'real']" in str(exc_info.value)

    def test_default_mode(self):
        """Test that default mode is mock when not specified."""
        inputs = {}  # No mode specified
        mode = resolve_mode(inputs)
        assert mode.value == "mock"
        assert is_mock(mode)

    @mock.patch.dict(os.environ, {"CI": ""}, clear=True)
    def test_case_insensitive_mode(self):
        """Test that mode parsing is case insensitive when not in CI."""
        for mode_value in ["MOCK", "Mock", "mock", "REAL", "Real", "real"]:
            inputs = {"mode": mode_value}
            mode = resolve_mode(inputs)
            assert mode.value == mode_value.lower()

    def test_none_inputs(self):
        """Test that None inputs defaults to mock mode."""
        mode = resolve_mode(None)
        assert mode.value == "mock"
        assert is_mock(mode)

    @mock.patch.dict(os.environ, {"CI": "true"})
    def test_ci_allows_real_mode(self):
        """Test that real mode works even in CI environment now."""
        inputs = {"mode": "real"}
        mode = resolve_mode(inputs)
        assert mode.value == "real"

    @mock.patch.dict(os.environ, {"CI": "true"})
    def test_ci_allows_mock_mode(self):
        """Test that mock mode works fine in CI environment."""
        inputs = {"mode": "mock"}
        mode = resolve_mode(inputs)
        assert mode.value == "mock"
        assert is_mock(mode)
