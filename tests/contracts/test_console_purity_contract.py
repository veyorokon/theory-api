"""Contract test: console purity for HTTP-first processors."""

import json
import subprocess
import pytest
from pathlib import Path


@pytest.mark.contracts
def test_console_purity_with_json_flag():
    """Contract: HTTP-first processors write clean JSON to stdout, structured logs to stderr."""

    # Run run_processor with --json flag
    result = subprocess.run(
        [
            "python",
            "manage.py",
            "run_processor",
            "--ref",
            "llm/litellm@1",
            "--adapter",
            "local",
            "--mode",
            "mock",
            "--write-prefix",
            "/artifacts/outputs/test/{execution_id}/",
            "--inputs-json",
            '{"schema":"v1","params":{"messages":[{"role":"user","content":"test"}]}}',
            "--json",
        ],
        cwd=str(Path(__file__).resolve().parents[2] / "code"),
        capture_output=True,
        text=True,
        timeout=30,
    )

    # Stdout must be exactly one JSON line
    stdout_lines = result.stdout.strip().split("\n")
    assert len(stdout_lines) == 1, f"Expected exactly 1 line in stdout, got {len(stdout_lines)}: {stdout_lines}"

    # Stdout must be valid JSON (envelope)
    try:
        envelope = json.loads(stdout_lines[0])
        assert "status" in envelope, "Envelope must have status field"
        assert "execution_id" in envelope, "Envelope must have execution_id field"
    except json.JSONDecodeError as e:
        pytest.fail(f"Stdout is not valid JSON: {e}")

    # All logs must be in stderr (if any)
    # We expect structured logs to be in stderr when --json is used
    if result.stderr:
        # Stderr should contain structured JSON logs, not envelope
        stderr_lines = result.stderr.strip().split("\n")
        for line in stderr_lines:
            if line.strip():  # Skip empty lines
                try:
                    log_entry = json.loads(line)
                    # Should have log structure, not envelope structure
                    assert "event" in log_entry or "level" in log_entry, (
                        f"Expected log structure in stderr, got: {line}"
                    )
                except json.JSONDecodeError:
                    # Some lines might be non-JSON (like warnings), which is acceptable in stderr
                    pass


@pytest.mark.contracts
def test_no_json_flag_allows_mixed_output():
    """Contract: Without --json flag, mixed output is allowed."""

    # Run run_processor WITHOUT --json flag
    result = subprocess.run(
        [
            "python",
            "manage.py",
            "run_processor",
            "--ref",
            "llm/litellm@1",
            "--adapter",
            "local",
            "--mode",
            "mock",
            "--write-prefix",
            "/artifacts/outputs/test/{execution_id}/",
            "--inputs-json",
            '{"schema":"v1","params":{"messages":[{"role":"user","content":"test"}]}}',
        ],
        cwd=str(Path(__file__).resolve().parents[2] / "code"),
        capture_output=True,
        text=True,
        timeout=30,
    )

    # Without --json, stdout can contain logs and envelope
    # This test just ensures the command works without --json
    assert result.returncode == 0, f"Command failed: {result.stderr}"
    assert result.stdout, "Should have some stdout output"
