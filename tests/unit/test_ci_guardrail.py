"""Test clean mode system validation."""

import pytest

from libs.runtime_common.mode import resolve_mode, is_mock, is_real


class TestModeSystem:
    """Test the clean two-mode system."""

    def test_mock_mode_validation(self):
        """Test that mock mode is parsed correctly."""
        inputs = {"mode": "mock"}
        mode = resolve_mode(inputs)
        assert mode.value == "mock"
        assert is_mock(mode)
        assert not is_real(mode)

    def test_real_mode_validation(self):
        """Test that real mode is parsed correctly."""
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

    def test_case_insensitive_mode(self):
        """Test that mode parsing is case insensitive."""
        for mode_value in ["MOCK", "Mock", "mock", "REAL", "Real", "real"]:
            inputs = {"mode": mode_value}
            mode = resolve_mode(inputs)
            assert mode.value == mode_value.lower()

    def test_none_inputs(self):
        """Test that None inputs defaults to mock mode."""
        mode = resolve_mode(None)
        assert mode.value == "mock"
        assert is_mock(mode)
