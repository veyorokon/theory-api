"""Clean subprocess helper for tests - uses sys.executable with env merging."""

import os
import sys
import subprocess
from typing import Dict, Optional, List


def run_py(
    args: List[str], *, cwd: str | None = None, extra_env: Dict[str, str] | None = None, check: bool = True, **kwargs
) -> subprocess.CompletedProcess:
    """Run Python subprocess with sys.executable and proper env merging.

    Args:
        args: Command args (e.g., ["manage.py", "test"])
        cwd: Working directory
        extra_env: Extra environment variables to merge (doesn't clobber PATH)
        check: Raise on non-zero exit code
        **kwargs: Additional subprocess.run arguments

    Returns:
        CompletedProcess result
    """
    env = {**os.environ, **(extra_env or {})}  # merge, don't replace
    return subprocess.run([sys.executable, *args], cwd=cwd, env=env, check=check, **kwargs)


def run_manage_py(
    command: str, *args: str, cwd: str = "code", extra_env: Dict[str, str] | None = None, **kwargs
) -> subprocess.CompletedProcess:
    """Run Django management command with proper environment.

    Args:
        command: Management command name (e.g., "build_processor")
        *args: Additional command arguments
        cwd: Working directory (defaults to "code")
        extra_env: Extra environment variables
        **kwargs: Additional subprocess.run arguments
    """
    cmd_args = ["manage.py", command, *args]
    return run_py(cmd_args, cwd=cwd, extra_env=extra_env, **kwargs)
