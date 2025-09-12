"""
Robust project root detection for Theory API.

Finds the theory_api project root directory using multiple detection methods
to avoid brittle relative path traversal.
"""

from pathlib import Path
import os
import subprocess

# Marker file to detect repo root; use README.md which is stable
MARKER = Path("README.md")


def find_project_root(start: Path | None = None) -> Path:
    """
    Find theory_api project root using multiple detection methods.

    Detection order:
    1. THEORY_API_ROOT environment variable (explicit override)
    2. Git repository root (fast and reliable)
    3. Marker file search walking up directory tree

    Args:
        start: Starting path for search (defaults to current file location)

    Returns:
        Path to project root directory

    Raises:
        RuntimeError: If project root cannot be determined
    """
    if start is None:
        start = Path(__file__).resolve()

    # 1) Environment variable override
    env_root = os.getenv("THEORY_API_ROOT")
    if env_root:
        root = Path(env_root).resolve()
        if (root / MARKER).exists():
            return root
        raise RuntimeError(f"THEORY_API_ROOT={root} missing {MARKER}")

    # 2) Git repository root
    try:
        # Use parent directory if start is a file
        search_dir = start if start.is_dir() else start.parent
        result = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"], cwd=str(search_dir), text=True, stderr=subprocess.DEVNULL
        ).strip()
        root = Path(result)
        if (root / MARKER).exists():
            return root
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Git not available or not in git repo
        pass

    # 3) Marker file search - walk up directory tree
    current = start if start.is_dir() else start.parent
    for parent in [current, *current.parents]:
        if (parent / MARKER).exists():
            return parent

    raise RuntimeError(
        f"Could not locate theory_api project root from {start}. Expected to find {MARKER} in repository root."
    )
