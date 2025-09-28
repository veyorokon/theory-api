"""
Integration test ensuring Modal adapter and management commands use consistent naming.
"""

import pytest
from unittest import mock

from apps.core.management.commands._modal_common import modal_app_name


@pytest.mark.integration
def test_modal_naming_consistency_dev():
    """Test naming consistency in dev environment (branch-user prefixed)."""
    processor_ref = "llm/litellm@1"

    # Test dev naming pattern directly
    app_name = modal_app_name(processor_ref, env="dev", branch="test-branch", user="test-user")

    # Should use dev naming pattern
    assert app_name == "test-branch-test-user-llm-litellm-v1"


@pytest.mark.integration
def test_modal_naming_consistency_staging():
    """Test naming consistency in staging environment (canonical names)."""
    processor_ref = "llm/litellm@1"

    # Test staging naming pattern directly
    app_name = modal_app_name(processor_ref, env="staging")

    # Should use canonical naming pattern
    assert app_name == "llm-litellm-v1"


@pytest.mark.integration
def test_modal_naming_consistency_main():
    """Test naming consistency in main environment (canonical names)."""
    processor_ref = "llm/litellm@1"

    # Test main naming pattern directly
    app_name = modal_app_name(processor_ref, env="main")

    # Should use canonical naming pattern
    assert app_name == "llm-litellm-v1"
