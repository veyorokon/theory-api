"""
Shared naming utilities for Modal app and function names.

Ensures consistency between modal_app.py deployment and ModalAdapter invocation.
"""


def modal_app_name(slug: str, ver: str, env: str) -> str:
    """
    Generate Modal app name from processor reference components.

    Args:
        slug: Processor slug (e.g., "llm-litellm" from "llm/litellm")
        ver: Version (e.g., "1" or "v1")
        env: Environment ("dev", "staging", "main")

    Returns:
        Modal app name: "{slug}-v{ver}-{env}"

    Examples:
        >>> modal_app_name("llm-litellm", "1", "dev")
        'llm-litellm-v1-dev'
        >>> modal_app_name("voice-clone", "v2", "staging")
        'voice-clone-v2-staging'
    """
    # Ensure version has v prefix
    ver_s = f"v{ver}" if not ver.startswith("v") else ver
    return f"{slug}-{ver_s}-{env}"


def modal_fn_name() -> str:
    """
    Generate Modal function name.

    Returns:
        Function name: "run" (standardized across all processors)
    """
    return "run"


def parse_processor_ref(processor_ref: str) -> tuple[str, str]:
    """
    Parse processor reference into slug and version components.

    Args:
        processor_ref: Reference like "llm/litellm@1" or "voice/clone@v2"

    Returns:
        Tuple of (slug, version) where slug has "/" replaced with "-"

    Examples:
        >>> parse_processor_ref("llm/litellm@1")
        ('llm-litellm', '1')
        >>> parse_processor_ref("voice/clone@v2")
        ('voice-clone', 'v2')
    """
    if "@" not in processor_ref:
        raise ValueError(f"Invalid processor reference: {processor_ref} (expected format: 'ns/name@ver')")

    name_part, version = processor_ref.split("@", 1)
    slug = name_part.replace("/", "-").lower()
    return slug, version


def modal_app_name_from_ref(processor_ref: str, env: str) -> str:
    """
    Generate Modal app name directly from processor reference.

    Args:
        processor_ref: Reference like "llm/litellm@1"
        env: Environment ("dev", "staging", "main")

    Returns:
        Modal app name

    Examples:
        >>> modal_app_name_from_ref("llm/litellm@1", "dev")
        'llm-litellm-v1-dev'
    """
    slug, ver = parse_processor_ref(processor_ref)
    return modal_app_name(slug, ver, env)
