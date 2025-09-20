"""
Shared naming utilities for Modal app and function names.

Ensures consistency between modal_app.py deployment and ModalAdapter invocation.
"""


def modal_fn_name() -> str:
    """
    Generate Modal function name.

    Returns:
        Function name: "run" (standardized across all processors)
    """
    return "run"


def modal_app_name_from_ref(processor_ref: str) -> str:
    """
    Deterministic processor app name, independent of environment.

    Args:
        processor_ref: Reference like "llm/litellm@1"

    Returns:
        Clean processor name: "llm-litellm-v1"

    Examples:
        >>> modal_app_name_from_ref("llm/litellm@1")
        'llm-litellm-v1'
        >>> modal_app_name_from_ref("replicate/generic@1")
        'replicate-generic-v1'
    """
    if "@" not in processor_ref:
        raise ValueError(f"Invalid processor reference: {processor_ref} (expected format: 'ns/name@ver')")

    ns_name, ver = processor_ref.split("@", 1)
    ns, name = ns_name.split("/", 1)

    # Clean naming: ns-name-vN
    ns_clean = ns.replace("_", "-").lower()
    name_clean = name.replace("_", "-").lower()
    ver_clean = f"v{ver}" if not ver.startswith("v") else ver

    return f"{ns_clean}-{name_clean}-{ver_clean}"
