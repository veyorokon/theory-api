# tests/tools/runner.py
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path
from typing import Mapping, Any


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def code_dir() -> Path:
    return repo_root() / "code"


def run_cli(
    args: list[str], *, env: Mapping[str, str] | None = None, timeout: int = 120
) -> subprocess.CompletedProcess[str]:
    """Run a Django manage.py command with deterministic cwd and interpreter."""
    cmd = [sys.executable, "manage.py", *args]
    return subprocess.run(
        cmd,
        cwd=str(code_dir()),
        env=None if env is None else {**env},
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def parse_stdout_json_or_fail(proc: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    if proc.returncode != 0:
        raise AssertionError(f"CLI failed (rc={proc.returncode})\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise AssertionError(f"STDOUT not JSON:\n{proc.stdout}\nERR: {e}\nSTDERR:\n{proc.stderr}")
