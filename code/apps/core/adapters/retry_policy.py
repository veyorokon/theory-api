RETRYABLE = {
    "ERR_ADAPTER_INVOCATION": True,  # e.g., transient 5xx/timeouts (adapter should tag root cause)
    "ERR_OUTPUT_DUPLICATE": False,
    "ERR_IMAGE_UNPINNED": False,
    # "ERR_IMAGE_MISSING":    False,  # if you choose to add it
}


def is_retryable(code: str) -> bool:
    return RETRYABLE.get(code, False)
