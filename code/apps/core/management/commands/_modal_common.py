"""
Shared utilities for Modal management commands.
"""

import os
import subprocess
from dataclasses import dataclass
from typing import Optional

from libs.runtime_common.modal_naming import modal_app_name


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


def compute_modal_context(*, processor_ref: str) -> ModalContext:
    """
    Compute Modal context including app name based on environment.

    Args:
        processor_ref: Processor reference (e.g., "llm/litellm@1")

    Returns:
        ModalContext with all values resolved
    """
    env = os.getenv("MODAL_ENVIRONMENT", "dev")
    is_ci = os.getenv("CI", "false").lower() == "true"
    user = _guess_user()
    branch = _guess_branch()

    # Use shared naming utility for consistency
    if env == "dev":
        app_name = modal_app_name(processor_ref, env=env, branch=branch, user=user)
    else:
        app_name = modal_app_name(processor_ref, env=env)

    return ModalContext(
        environment=env,
        is_ci=is_ci,
        user=user,
        branch=branch,
        processor_ref=processor_ref,
        app_name=app_name,
    )
