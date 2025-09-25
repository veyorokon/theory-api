"""
Shared utilities for Modal management commands.
"""

import os
import subprocess
from dataclasses import dataclass

import re


def _slug(s: str) -> str:
    """Normalize string to valid app name component."""
    s = s.strip().lower()
    return re.sub(r"[^a-z0-9\-]+", "-", s)


def parse_ref(ref: str) -> tuple[str, str, int]:
    """Parse processor ref 'ns/name@v' where v is integer."""
    if "@" not in ref or "/" not in ref:
        raise ValueError("invalid processor ref")
    ns_name, ver = ref.split("@", 1)
    if "/" not in ns_name:
        raise ValueError("invalid processor ref")
    ns, name = ns_name.split("/", 1)
    if not ver.isdigit():
        raise ValueError("invalid version")
    return _slug(ns), _slug(name), int(ver)


def processor_slug(ref: str) -> str:
    """Convert ref to canonical processor slug: 'ns-name-vX'."""
    ns, name, ver = parse_ref(ref)
    return f"{ns}-{name}-v{ver}"


def modal_app_name(ref: str, *, env: str, branch: str | None = None, user: str | None = None) -> str:
    """
    Return Modal App name for a processor ref under an environment.

    dev:          <branch>-<user>-<ns>-<name>-vX
    staging/main: <ns>-<name>-vX
    """
    base = processor_slug(ref)
    env = (env or "").strip().lower()
    if env == "dev":
        if branch and user:
            return f"{_slug(branch)}-{_slug(user)}-{base}"
        raise ValueError("dev naming requires branch and user")
    return base


@dataclass(frozen=True)
class ModalContext:
    """Context for Modal operations with all resolved values."""

    environment: str
    is_ci: bool
    user: str | None
    branch: str | None
    processor_ref: str
    app_name: str


def _guess_user() -> str:
    """Get user from environment variables."""
    return (os.getenv("GITHUB_ACTOR") or os.getenv("USER") or "unknown").lower()


def _guess_branch() -> str:
    """Get branch from CI vars or git."""
    # Try CI environment variables first
    branch = (
        os.getenv("GITHUB_HEAD_REF")  # PR branch
        or os.getenv("GITHUB_REF_NAME")  # Push branch
        or os.getenv("BRANCH_NAME")  # Generic CI
    )

    if branch:
        return branch

    # Try local git
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, check=True, timeout=2
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return "local"
