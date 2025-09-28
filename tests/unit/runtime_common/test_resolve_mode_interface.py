"""Test resolve_mode interface compatibility and CI enforcement contracts."""

import pytest
from unittest.mock import patch

from libs.runtime_common.envelope import resolve_mode, ModeSafetyError


class TestResolveModeInterface:
    """Lock resolve_mode interface - prevents regressions."""

    @patch.dict("os.environ", {}, clear=True)
    def test_string_inputs(self):
        """Test string mode inputs."""
        assert resolve_mode("mock").value == "mock"
        assert resolve_mode("MOCK").value == "mock"  # Case insensitive
        assert resolve_mode("real").value == "real"
        assert resolve_mode("REAL").value == "real"
        assert resolve_mode(None).value == "mock"  # Default

    @patch.dict("os.environ", {}, clear=True)
    def test_dict_inputs_backward_compatibility(self):
        """Test dict inputs for backward compatibility."""
        # Dict with mode key
        assert resolve_mode({"mode": "mock"}).value == "mock"
        assert resolve_mode({"mode": "real"}).value == "real"
        assert resolve_mode({"mode": "MOCK"}).value == "mock"

        # Dict with other data (should ignore)
        assert resolve_mode({"mode": "mock", "other": "data"}).value == "mock"

        # Empty dict (no mode key)
        assert resolve_mode({}).value == "mock"

    def test_invalid_modes_rejected(self):
        """Test that invalid modes are rejected."""
        with pytest.raises(ValueError, match="Invalid mode 'invalid'"):
            resolve_mode("invalid")

        with pytest.raises(ValueError, match="Invalid mode 'smoke'"):
            resolve_mode({"mode": "smoke"})

    @patch.dict("os.environ", {"TEST_LANE": "pr"}, clear=False)
    def test_real_mode_allowed_in_pr_lane(self):
        """Real mode is allowed even in PR lane now."""
        # Both mock and real should work
        assert resolve_mode("mock").value == "mock"
        assert resolve_mode({"mode": "mock"}).value == "mock"
        assert resolve_mode("real").value == "real"
        assert resolve_mode({"mode": "real"}).value == "real"

    @patch.dict("os.environ", {}, clear=True)
    def test_non_ci_allows_real_mode(self):
        """Test that real mode works when not in CI."""
        assert resolve_mode("real").value == "real"
        assert resolve_mode({"mode": "real"}).value == "real"

    @patch.dict("os.environ", {"LANE": "pr"}, clear=False)
    def test_pr_lane_allows_real_mode(self):
        """LANE=pr no longer blocks mode=real."""
        assert resolve_mode("real").value == "real"

    @patch.dict("os.environ", {"TEST_LANE": "pr"}, clear=False)
    def test_test_lane_allows_real_mode(self):
        """TEST_LANE=pr no longer blocks mode=real."""
        assert resolve_mode("real").value == "real"
