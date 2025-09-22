"""
Retry policy for error codes.

Maps each error code to whether it should be retried.
Transient errors (network, timeouts) are retryable.
Permanent errors (validation, missing resources) are not.
"""

RETRYABLE = {
    # Transient errors - should retry (network, remote timeouts)
    "ERR_MODAL_TIMEOUT": True,  # Network/remote timeouts
    "ERR_MODAL_LOOKUP": True,  # Temporary service unavailability
    "ERR_MODAL_INVOCATION": True,  # Remote execution failures (could be transient)
    "ERR_IMAGE_PULL": True,  # Network issues pulling image
    # Permanent errors - should not retry (configuration, validation, missing resources)
    "ERR_ADAPTER_INVOCATION": False,  # Contract violations, missing args
    "ERR_OUTPUT_DUPLICATE": False,  # Data integrity issues
    "ERR_CI_SAFETY": False,  # Environment safety violations
    "ERR_MISSING_SECRET": False,  # Configuration errors
    "ERR_SECRET_MISSING": False,  # Configuration errors (legacy)
    "ERR_INPUTS": False,  # Invalid input data
    "ERR_MODAL_PAYLOAD": False,  # Invalid payload structure
    "ERR_IMAGE_UNPINNED": False,  # Supply chain violations
    "ERR_IMAGE_UNAVAILABLE": False,  # Image not found (permanent)
    "ERR_REGISTRY_MISMATCH": False,  # Registry configuration errors
    "ERR_DECODED_SLASH": False,
    "ERR_DOT_SEGMENTS": False,
    "ERR_PATH_TOO_LONG": False,
    "ERR_SEGMENT_TOO_LONG": False,
    "ERR_FORBIDDEN_SEGMENT": False,
    "ERR_PREFIX_TEMPLATE": False,
    "ERR_FUNCTION_NOT_FOUND": False,
}


def is_retryable(code: str) -> bool:
    """Check if an error code indicates a retryable failure."""
    return RETRYABLE.get(code, False)
