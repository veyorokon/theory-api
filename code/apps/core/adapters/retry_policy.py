"""
Retry policy for error codes.

Maps each error code to whether it should be retried.
Transient errors (network, timeouts) are retryable.
Permanent errors (validation, missing resources) are not.
"""

RETRYABLE = {
    # Transient errors - should retry
    "ERR_ADAPTER_INVOCATION": True,  # 5xx/timeouts
    "ERR_IMAGE_PULL": True,  # Network issues pulling image
    # Permanent errors - should not retry
    "ERR_OUTPUT_DUPLICATE": False,
    "ERR_IMAGE_UNPINNED": False,
    "ERR_MISSING_SECRET": False,
    "ERR_SECRET_MISSING": False,
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
