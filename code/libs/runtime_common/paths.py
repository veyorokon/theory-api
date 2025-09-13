"""Write prefix validation utilities."""

from pathlib import PurePosixPath


class PrefixError(Exception):
    """Raised when write prefix validation fails."""
    pass


ALLOWED_ROOT = PurePosixPath("/artifacts")


def validate_write_prefix(prefix: str, execution_id: str) -> str:
    """
    Expand {execution_id}, ensure trailing '/', normalize, and enforce allowed root.
    Returns the normalized prefix (always ends with '/').
    Raises PrefixError on invalid input.
    """
    if "{execution_id}" in prefix:
        prefix = prefix.replace("{execution_id}", execution_id)

    if not prefix.endswith("/"):
        raise PrefixError("write_prefix must end with '/'")
    
    if not prefix.startswith("/"):
        raise PrefixError("write_prefix must start with '/'")

    # Normalize without touching host FS
    p = PurePosixPath(prefix)
    # Collapse to remove '..' and '.' segments - use prefix directly since it's already absolute
    norm = p.as_posix()

    # Enforce allowed root
    if not norm.startswith(ALLOWED_ROOT.as_posix() + "/") and norm != (ALLOWED_ROOT.as_posix() + "/"):
        raise PrefixError(f"write_prefix must be under {ALLOWED_ROOT.as_posix()}/")

    # Block any parent traversal explicitly
    if ".." in p.parts:
        raise PrefixError("write_prefix must not contain '..'")

    # Ensure trailing slash for adapter compatibility
    if not norm.endswith("/"):
        norm += "/"
    
    return norm