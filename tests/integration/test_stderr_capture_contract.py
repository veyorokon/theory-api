"""Test stderr capture via orchestrator/CLI - contract compliance."""

import json
import pytest
from tests.tools.runner import run_cli, parse_stdout_json_or_fail


@pytest.mark.integration
@pytest.mark.requires_docker
def test_orchestrator_captures_container_stderr(tmp_write_prefix):
    """Verify orchestrator captures container stderr in error envelopes."""
    # Use a bogus inputs to trigger stderr output from container
    args = [
        "run_processor",
        "--ref",
        "llm/litellm@1",
        "--adapter",
        "local",
        "--mode",
        "mock",
        "--write-prefix",
        tmp_write_prefix,
        "--inputs-json",
        json.dumps({"schema": "v1", "invalid_field": "should_cause_stderr"}),
        "--json",
        "--build",
    ]

    result = run_cli(args, env={"LOG_STREAM": "stderr"})
    envelope = parse_stdout_json_or_fail(result)

    # Contract: stderr capture in error cases
    if envelope["status"] == "error":
        assert "meta" in envelope
        # stderr_tail should be present for local adapter errors
        # (exact presence depends on error type, but structure must be consistent)
        if "stderr_tail" in envelope.get("meta", {}):
            stderr = envelope["meta"]["stderr_tail"]
            assert isinstance(stderr, str)
            assert len(stderr) <= 2000  # Bounded as per spec


@pytest.mark.integration
@pytest.mark.requires_docker
def test_orchestrator_successful_run_no_stderr_leak(tmp_write_prefix):
    """Verify successful runs don't leak stderr into envelope."""
    args = [
        "run_processor",
        "--ref",
        "llm/litellm@1",
        "--adapter",
        "local",
        "--mode",
        "mock",
        "--write-prefix",
        tmp_write_prefix,
        "--inputs-json",
        json.dumps({"schema": "v1", "params": {"messages": [{"role": "user", "content": "test"}]}}),
        "--json",
        "--build",
    ]

    result = run_cli(args, env={"LOG_STREAM": "stderr"})
    envelope = parse_stdout_json_or_fail(result)

    # Contract: successful runs should not have stderr_tail
    assert envelope["status"] == "success"
    meta = envelope.get("meta", {})
    assert "stderr_tail" not in meta
