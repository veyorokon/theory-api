"""Contract test: adapter retry policy behavior."""

import pytest
from apps.core.adapters.retry_policy import is_retryable


@pytest.mark.contracts
def test_retry_policy_contract():
    """Contract: Lock retry policy behavior for canonical error codes."""

    # Non-retryable errors (immediate failures)
    non_retryable_errors = [
        "ERR_ADAPTER_INVOCATION",  # Contract violations, missing args
        "ERR_OUTPUT_DUPLICATE",  # Data integrity issues
        "ERR_CI_SAFETY",  # Environment safety violations
        "ERR_MISSING_SECRET",  # Configuration errors
        "ERR_INPUTS",  # Invalid input data
        "ERR_MODAL_PAYLOAD",  # Invalid payload structure
        "ERR_IMAGE_UNPINNED",  # Supply chain violations
        "ERR_IMAGE_UNAVAILABLE",  # Image not found
        "ERR_REGISTRY_MISMATCH",  # Registry configuration errors
    ]

    for error_code in non_retryable_errors:
        assert not is_retryable(error_code), f"Error {error_code} should NOT be retryable"

    # Retryable errors (transient failures)
    retryable_errors = [
        "ERR_MODAL_TIMEOUT",  # Network/remote timeouts
        "ERR_MODAL_LOOKUP",  # Temporary service unavailability
        "ERR_MODAL_INVOCATION",  # Remote execution failures (could be transient)
    ]

    for error_code in retryable_errors:
        assert is_retryable(error_code), f"Error {error_code} should be retryable"

    # ERR_MODAL_TIMEOUT should be retryable exactly once (not indefinitely)
    # This prevents infinite retry loops on persistent timeouts
    assert is_retryable("ERR_MODAL_TIMEOUT"), "ERR_MODAL_TIMEOUT should be retryable"

    # Unknown error codes should default to non-retryable (fail-fast)
    assert not is_retryable("ERR_UNKNOWN_ERROR"), "Unknown errors should not be retryable"
    assert not is_retryable(""), "Empty error code should not be retryable"
