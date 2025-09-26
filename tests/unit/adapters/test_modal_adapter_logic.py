"""Unit tests for Modal adapter URL resolution and error mapping logic."""

import pytest
from unittest.mock import Mock, patch
from apps.core.adapters.modal_adapter import ModalHTTPAdapter, ModalInvokeOptions
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

    @patch("builtins.__import__")
    def test_modal_url_resolution_success(self, mock_import):
        """Test successful URL resolution from Modal SDK."""
        # Mock the modal module import
        mock_modal = Mock()
        mock_app = Mock()
        mock_function = Mock()
        mock_function.web_url = "https://modal-function-url.com"
        mock_app.function.return_value = mock_function
        mock_modal.App.lookup.return_value = mock_app

        def mock_import_func(name, *args, **kwargs):
            if name == "modal":
                return mock_modal
            else:
                # Fall back to real import for other modules
                return __import__(name, *args, **kwargs)

        mock_import.side_effect = mock_import_func

        adapter = ModalHTTPAdapter()
        url = adapter._get_modal_web_url("test-app", "fastapi_app", env="dev")

        assert url == "https://modal-function-url.com"
        mock_modal.App.lookup.assert_called_once_with("test-app", environment="dev")
        mock_app.function.assert_called_once_with("fastapi_app")

    @patch("builtins.__import__")
    def test_modal_url_resolution_app_not_found(self, mock_import):
        """Test error handling when Modal app not found."""
        mock_modal = Mock()
        mock_modal.App.lookup.side_effect = Exception("App not found")

        def mock_import_func(name, *args, **kwargs):
            if name == "modal":
                return mock_modal
            else:
                return __import__(name, *args, **kwargs)

        mock_import.side_effect = mock_import_func

        adapter = ModalHTTPAdapter()

        with pytest.raises(Exception, match="App not found"):
            adapter._get_modal_web_url("missing-app", "fastapi_app", env="dev")

    @patch("builtins.__import__")
    def test_modal_url_resolution_no_web_url(self, mock_import):
        """Test error handling when function has no web_url."""
        mock_modal = Mock()
        mock_app = Mock()
        mock_function = Mock()
        mock_function.web_url = None  # No URL available
        mock_app.function.return_value = mock_function
        mock_modal.App.lookup.return_value = mock_app

        def mock_import_func(name, *args, **kwargs):
            if name == "modal":
                return mock_modal
            else:
                return __import__(name, *args, **kwargs)

        mock_import.side_effect = mock_import_func

        adapter = ModalHTTPAdapter()

        with pytest.raises(RuntimeError, match="has no web_url"):
            adapter._get_modal_web_url("test-app", "fastapi_app", env="dev")

    @patch("builtins.__import__")
    def test_invoke_by_ref_error_envelope(self, mock_import):
        """Test error envelope generation when URL resolution fails."""
        mock_modal = Mock()
        mock_modal.App.lookup.side_effect = Exception("App not deployed")

        def mock_import_func(name, *args, **kwargs):
            if name == "modal":
                return mock_modal
            else:
                return __import__(name, *args, **kwargs)

        mock_import.side_effect = mock_import_func

        adapter = ModalHTTPAdapter()
        options = ModalInvokeOptions(app_name="missing-app", env="dev")
        payload = {"execution_id": "test-exec-id", "schema": "v1"}

        result = adapter.invoke(ref="llm/litellm@1", payload=payload, options=options)

        assert result.status == "error"
        assert result.envelope["status"] == "error"
        assert result.envelope["execution_id"] == "test-exec-id"
        assert result.envelope["error"]["code"] == "ERR_ENDPOINT_MISSING"
        assert "Modal URL resolution failed" in result.envelope["error"]["message"]

    def test_invoke_uses_explicit_app_name(self):
        """Test that invoke uses explicit app_name when provided."""
        with patch.object(ModalHTTPAdapter, "_get_modal_web_url") as mock_get_url:
            mock_get_url.return_value = "https://test-url.com"

            # Mock the _http instance variable
            adapter = ModalHTTPAdapter()
            adapter._http = Mock()
            adapter._http.invoke.return_value = Mock(status="success", envelope={})

            options = ModalInvokeOptions(app_name="explicit-app", env="dev")
            payload = {"execution_id": "test-exec-id"}

            adapter.invoke(ref="llm/litellm@1", payload=payload, options=options)

            mock_get_url.assert_called_once_with("explicit-app", "fastapi_app", env="dev")

    def test_invoke_derives_app_name_when_not_provided(self):
        """Test that invoke derives app_name from ref when not explicitly provided."""
        with patch.object(ModalHTTPAdapter, "_get_modal_web_url") as mock_get_url:
            mock_get_url.return_value = "https://test-url.com"

            # Mock the _http instance variable
            adapter = ModalHTTPAdapter()
            adapter._http = Mock()
            adapter._http.invoke.return_value = Mock(status="success", envelope={})

            options = ModalInvokeOptions(env="dev", branch="main", user="alice")
            payload = {"execution_id": "test-exec-id"}

            adapter.invoke(ref="llm/litellm@1", payload=payload, options=options)

            # Should derive app name: main-alice-llm-litellm-v1 (dev pattern)
            expected_app_name = "main-alice-llm-litellm-v1"
            mock_get_url.assert_called_once_with(expected_app_name, "fastapi_app", env="dev")
