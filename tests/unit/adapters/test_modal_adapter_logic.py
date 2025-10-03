"""Unit tests for Modal adapter URL resolution and error mapping logic."""

import pytest
from unittest.mock import Mock, patch
from apps.core.adapters.modal_ws_adapter import ModalWsAdapter
from apps.core.management.commands._modal_common import modal_app_name


class TestModalAdapterLogic:
    """Test Modal adapter core logic without Modal SDK dependencies."""

    def test_app_name_derivation(self):
        """Test app name derivation using canonical naming function."""
        ref = "llm/litellm@1"

        # Test staging/main (no branch/user needed)
        result = modal_app_name(ref, env="staging")
        assert result == "llm-litellm-v1"

        # Test dev with branch and user
        result = modal_app_name(ref, env="dev", branch="feat/test-branch", user="alice")
        assert result == "feat-test-branch-alice-llm-litellm-v1"

        # Test underscore replacement
        ref_with_underscore = "ns/my_processor@2"
        result = modal_app_name(ref_with_underscore, env="staging")
        assert result == "ns-my-processor-v2"

    @patch("modal.Function.from_name")
    def test_modal_url_resolution_success(self, mock_from_name):
        """Test successful URL resolution from Modal SDK."""
        from apps.core.utils.adapters import _get_modal_web_url

        # Mock the function object returned by from_name
        mock_function = Mock()
        mock_function.get_web_url.return_value = "https://modal-function-url.com"
        mock_function.web_url = "https://modal-function-url.com"
        mock_from_name.return_value = mock_function

        url = _get_modal_web_url("test-app", "fastapi_app")

        assert url == "https://modal-function-url.com"
        mock_from_name.assert_called_once_with("test-app", "fastapi_app")

    @patch("modal.Function.from_name")
    def test_modal_url_resolution_app_not_found(self, mock_from_name):
        """Test error handling when Modal app not found."""
        from apps.core.utils.adapters import _get_modal_web_url

        mock_from_name.side_effect = Exception("App not found")

        with pytest.raises(RuntimeError, match="Modal function lookup failed"):
            _get_modal_web_url("missing-app", "fastapi_app")

    @patch("modal.Function.from_name")
    def test_modal_url_resolution_no_web_url(self, mock_from_name):
        """Test error handling when function has no web_url."""
        from apps.core.utils.adapters import _get_modal_web_url

        mock_function = Mock()
        mock_function.get_web_url.return_value = None
        mock_function.web_url = None  # No URL available
        mock_from_name.return_value = mock_function

        with pytest.raises(RuntimeError, match="has no web_url"):
            _get_modal_web_url("test-app", "fastapi_app")
