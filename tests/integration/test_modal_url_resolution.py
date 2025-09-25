"""Modal SDK URL resolution integration tests."""

import pytest
from unittest.mock import patch, MagicMock


pytestmark = [pytest.mark.integration]


class TestModalURLResolution:
    """Test ModalAdapter uses Modal SDK for URL resolution."""

    def test_modal_adapter_uses_sdk_not_string_concat(self):
        """Test ModalAdapter resolves URLs via Modal SDK, not string concatenation."""
        from apps.core.adapters.modal_adapter import ModalAdapter
        from apps.core.management.commands._modal_common import modal_app_name

        # Mock Modal SDK components
        with patch("modal.lookup") as mock_lookup, patch("requests.post") as mock_post:
            # Mock Modal function with web_url property
            mock_function = MagicMock()
            mock_function.web_url = "https://mock-modal-url.modal.run"

            mock_app = MagicMock()
            mock_app.__getitem__.return_value = mock_function
            mock_lookup.return_value = mock_app

            # Mock HTTP response
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "status": "success",
                "execution_id": "test-123",
                "outputs": [],
                "meta": {"image_digest": "sha256:test123"},
            }
            mock_post.return_value = mock_response

            adapter = ModalAdapter()

            payload = {
                "execution_id": "test-123",
                "write_prefix": "/artifacts/outputs/test/",
                "schema": "v1",
                "mode": "mock",
                "params": {"messages": [{"role": "user", "content": "test"}]},
            }

            # Set expected environment
            import os

            os.environ.update({"MODAL_ENVIRONMENT": "dev", "BRANCH": "feat/test", "USER": "testuser"})

            result = adapter.invoke(processor_ref="llm/litellm@1", payload=payload, timeout_s=60)

            # Verify SDK was used
            expected_app_name = modal_app_name("llm/litellm@1", env="dev", branch="feat/test", user="testuser")
            mock_lookup.assert_called_once_with(expected_app_name, environment="dev")

            # Verify no string concatenation in URL construction
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            posted_url = call_args[0][0]

            # URL should come from SDK, not be constructed via string formatting
            assert posted_url == f"{mock_function.web_url}/run"
            assert "mock-modal-url.modal.run" in posted_url

            # Verify result
            assert result["status"] == "success"

    def test_modal_function_name_consistency(self):
        """Test Modal function name matches expected deployment pattern."""
        from apps.core.management.commands._modal_common import modal_app_name

        # Test dev environment naming
        dev_name = modal_app_name("llm/litellm@1", env="dev", branch="feat/test-branch", user="testuser")
        assert dev_name == "feat-test-branch-testuser-llm-litellm-v1"

        # Test staging environment naming
        staging_name = modal_app_name("llm/litellm@1", env="staging")
        assert staging_name == "llm-litellm-v1"

        # Test main environment naming
        main_name = modal_app_name("llm/litellm@1", env="main")
        assert main_name == "llm-litellm-v1"

    def test_modal_sdk_error_handling(self):
        """Test ModalAdapter handles SDK errors gracefully."""
        from apps.core.adapters.modal_adapter import ModalAdapter

        # Test app not found
        with patch("modal.lookup") as mock_lookup:
            mock_lookup.side_effect = Exception("App not found")

            adapter = ModalAdapter()

            payload = {
                "execution_id": "test-error",
                "write_prefix": "/artifacts/outputs/error/",
                "schema": "v1",
                "mode": "mock",
                "params": {"messages": [{"role": "user", "content": "error test"}]},
            }

            import os

            os.environ.update({"MODAL_ENVIRONMENT": "dev", "BRANCH": "feat/test", "USER": "testuser"})

            result = adapter.invoke(processor_ref="llm/litellm@1", payload=payload, timeout_s=60)

            # Should return error envelope
            assert result["status"] == "error"
            assert "ERR_MODAL_LOOKUP" in result["error"]["code"]

    def test_modal_function_lookup_by_name(self):
        """Test Modal adapter looks up specific function by name."""
        from apps.core.adapters.modal_adapter import ModalAdapter

        with patch("modal.lookup") as mock_lookup, patch("requests.post") as mock_post:
            # Mock Modal app with multiple functions
            mock_function = MagicMock()
            mock_function.web_url = "https://test-url.modal.run"

            mock_app = MagicMock()
            mock_app.__getitem__.return_value = mock_function

            mock_lookup.return_value = mock_app

            # Mock successful response
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "status": "success",
                "execution_id": "test-function",
                "outputs": [],
                "meta": {"image_digest": "sha256:test123"},
            }
            mock_post.return_value = mock_response

            adapter = ModalAdapter()

            payload = {
                "execution_id": "test-function",
                "write_prefix": "/artifacts/outputs/function/",
                "schema": "v1",
                "mode": "mock",
                "params": {"messages": [{"role": "user", "content": "function test"}]},
            }

            import os

            os.environ.update({"MODAL_ENVIRONMENT": "dev", "BRANCH": "feat/test", "USER": "testuser"})

            result = adapter.invoke(processor_ref="llm/litellm@1", payload=payload, timeout_s=60)

            # Verify function lookup by name
            mock_app.__getitem__.assert_called_once_with("fastapi_app")
            assert result["status"] == "success"

    def test_modal_environment_handling(self):
        """Test Modal adapter handles different environments correctly."""
        from apps.core.management.commands._modal_common import modal_app_name

        test_cases = [
            {
                "env": "dev",
                "branch": "feat/modal-test",
                "user": "devuser",
                "expected": "feat-modal-test-devuser-llm-litellm-v1",
            },
            {"env": "staging", "branch": None, "user": None, "expected": "llm-litellm-v1"},
            {"env": "main", "branch": None, "user": None, "expected": "llm-litellm-v1"},
        ]

        for case in test_cases:
            if case["env"] == "dev":
                app_name = modal_app_name("llm/litellm@1", env=case["env"], branch=case["branch"], user=case["user"])
            else:
                app_name = modal_app_name("llm/litellm@1", env=case["env"])

            assert app_name == case["expected"], (
                f"Environment {case['env']} produced {app_name}, expected {case['expected']}"
            )

    def test_modal_url_no_hardcoded_strings(self):
        """Test Modal adapter doesn't use hardcoded URL patterns."""
        from apps.core.adapters.modal_adapter import ModalAdapter

        with patch("modal.lookup") as mock_lookup, patch("requests.post") as mock_post:
            # Mock function with different URL pattern
            mock_function = MagicMock()
            mock_function.web_url = "https://completely-different-pattern-123xyz.modal.run"

            mock_app = MagicMock()
            mock_app.__getitem__.return_value = mock_function
            mock_lookup.return_value = mock_app

            # Mock response
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "status": "success",
                "execution_id": "url-test",
                "outputs": [],
                "meta": {"image_digest": "sha256:test123"},
            }
            mock_post.return_value = mock_response

            adapter = ModalAdapter()

            payload = {
                "execution_id": "url-test",
                "write_prefix": "/artifacts/outputs/url/",
                "schema": "v1",
                "mode": "mock",
                "params": {"messages": [{"role": "user", "content": "url test"}]},
            }

            import os

            os.environ.update({"MODAL_ENVIRONMENT": "dev", "BRANCH": "feat/url", "USER": "urluser"})

            result = adapter.invoke(processor_ref="llm/litellm@1", payload=payload, timeout_s=60)

            # Verify adapter used the SDK-provided URL, not a hardcoded pattern
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            used_url = call_args[0][0]

            assert "completely-different-pattern-123xyz.modal.run" in used_url
            assert used_url == f"{mock_function.web_url}/run"
            assert result["status"] == "success"
