"""
Secret resolution with single entry point.

All secret/environment lookups must go through these functions.
Direct os.getenv() calls are forbidden outside this module.
"""

import os
from typing import Mapping
from apps.core.errors import ERR_SECRET_MISSING


def get_secret(name: str, *, mode: str, env: Mapping[str, str]) -> str:
    if mode == "mock":
        raise RuntimeError("ERR_MISSING_SECRET: mock disallows secrets")
    # ... real resolution here ...
    value = env.get(name) or env.get(name.upper())
    if not value:
        raise RuntimeError(f"ERR_MISSING_SECRET: Required secret '{name}' not found")
    return value.strip()


def resolve_secret(name: str) -> str | None:
    """
    Resolve a secret by name, returning None if not found.

    Args:
        name: Secret name (case-insensitive lookup)

    Returns:
        Secret value or None
    """
    # Single entry-point: map registry secret names to env/material
    v = os.getenv(name) or os.getenv(name.upper())
    return v.strip() if v else None


def resolve_required(name: str) -> str:
    """
    Resolve a required secret, raising if not found.

    Args:
        name: Secret name (case-insensitive lookup)

    Returns:
        Secret value

    Raises:
        RuntimeError: If secret is missing
    """
    value = resolve_secret(name)
    if not value:
        raise RuntimeError(f"{ERR_SECRET_MISSING}: Required secret '{name}' not found")
    return value
