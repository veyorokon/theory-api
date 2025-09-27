"""CLI boundary contract tests - stdout/stderr separation."""

import json
import os
import subprocess
import sys
import pytest


@pytest.mark.integration
@pytest.mark.requires_docker
def test_cli_stdout_purity(tmp_path):
    """Verify CLI writes envelope to stdout, logs to stderr."""
    cmd = [
        sys.executable,
        "manage.py",
        "run_processor",
        "--ref",
        "llm/litellm@1",
        "--adapter",
        "local",
        "--mode",
        "mock",
        "--write-prefix",
        str(tmp_path / "{execution_id}/"),
        "--inputs-json",
        json.dumps({"schema": "v1", "params": {"messages": [{"role": "user", "content": "hi"}]}}),
        "--json",
        "--build",
    ]
    env = {**os.environ, "DJANGO_SETTINGS_MODULE": "backend.settings.unittest"}
    p = subprocess.run(cmd, cwd="code", env=env, text=True, capture_output=True, timeout=180)
    assert p.returncode == 0
    envlp = json.loads(p.stdout)  # stdout envelope only
    assert envlp["status"] in {"success", "error"}
    assert p.stderr  # NDJSON logs on stderr


@pytest.mark.integration
def test_cli_bad_flag_returns_error():
    """Verify CLI handles bad arguments gracefully."""
    cmd = [sys.executable, "manage.py", "run_processor", "--unknown-flag"]
    env = {**os.environ, "DJANGO_SETTINGS_MODULE": "backend.settings.unittest"}
    p = subprocess.run(cmd, cwd="code", env=env, text=True, capture_output=True, timeout=60)
    # Either Django errors cleanly, or we get our envelope; in both cases no stdout log noise.
    if p.stdout.strip():
        envlp = json.loads(p.stdout)
        assert envlp["status"] == "error"
        assert envlp["error"]["code"] in {"ERR_INPUTS", "ERR_ADAPTER"}
    else:
        assert "unrecognized arguments" in (p.stderr or "").lower() or "required" in (p.stderr or "").lower()
