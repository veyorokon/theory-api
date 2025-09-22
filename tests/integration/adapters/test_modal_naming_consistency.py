"""
Integration test ensuring Modal adapter and management commands use consistent naming.
"""

import pytest
from unittest import mock

from apps.core.management.commands._modal_common import compute_modal_context


@pytest.mark.integration
def test_modal_naming_consistency_dev():
    """Test naming consistency in dev environment (branch-user prefixed)."""
    processor_ref = "llm/litellm@1"

    # Mock git and environment to control naming
    with (
        mock.patch("apps.core.management.commands._modal_common._guess_branch", return_value="test-branch"),
        mock.patch("apps.core.management.commands._modal_common._guess_user", return_value="test-user"),
        mock.patch.dict("os.environ", {"MODAL_ENVIRONMENT": "dev"}),
    ):
        # Both adapter and management commands now use compute_modal_context
        ctx = compute_modal_context(processor_ref=processor_ref)
        app_name = ctx.app_name

        # Should use dev naming pattern
        assert app_name == "test-branch-test-user-llm-litellm-v1"


@pytest.mark.integration
def test_modal_naming_consistency_staging():
    """Test naming consistency in staging environment (canonical names)."""
    processor_ref = "llm/litellm@1"

    with mock.patch.dict("os.environ", {"MODAL_ENVIRONMENT": "staging"}):
        # Both adapter and management commands now use compute_modal_context
        ctx = compute_modal_context(processor_ref=processor_ref)
        app_name = ctx.app_name

        # Should use canonical naming pattern
        assert app_name == "llm-litellm-v1"


@pytest.mark.integration
def test_modal_naming_consistency_main():
    """Test naming consistency in main environment (canonical names)."""
    processor_ref = "llm/litellm@1"

    with mock.patch.dict("os.environ", {"MODAL_ENVIRONMENT": "main"}):
        # Both adapter and management commands now use compute_modal_context
        ctx = compute_modal_context(processor_ref=processor_ref)
        app_name = ctx.app_name

        # Should use canonical naming pattern
        assert app_name == "llm-litellm-v1"
