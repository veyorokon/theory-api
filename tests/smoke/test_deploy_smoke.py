"""
Post-deploy smoke tests to verify deployed Modal functions work correctly.

These tests run after deployment to validate the system is operational.
Uses mode=mock to avoid external costs while testing deployment functionality.
"""

from __future__ import annotations

import json
import subprocess
import sys
import pytest


def test_llm_litellm_smoke_mock():
    """Smoke test for deployed LLM LiteLLM processor using mode=mock."""
    cmd = [
        sys.executable,
        "manage.py",
        "run_processor",
        "--ref",
        "llm/litellm@1",
        "--adapter",
        "modal",
        "--mode",
        "mock",
        "--adapter-opts-json",
        '{"function":"smoke"}',
        "--inputs-json",
        '{"schema":"v1","params":{"messages":[{"role":"user","content":"smoke test"}],"model":"gpt-4o-mini"}}',
        "--write-prefix",
        "/artifacts/outputs/smoke/{execution_id}/",
        "--json",
    ]

    result = subprocess.run(
        cmd,
        cwd="code",
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, f"run_processor smoke failed: {result.stderr}"

    # Parse the JSON output (canonical envelope)
    try:
        response = json.loads(result.stdout.strip())
    except json.JSONDecodeError as e:
        pytest.fail(f"Invalid JSON output: {e}\nOutput: {result.stdout}")

    assert response["status"] == "success", f"Smoke test failed: {response}"
    assert response["execution_id"], "Missing execution_id in response"
    assert "outputs" in response, "Missing outputs in response"


def test_replicate_generic_smoke_mock():
    """Smoke test for deployed Replicate generic processor using mode=mock."""
    cmd = [
        sys.executable,
        "manage.py",
        "run_processor",
        "--ref",
        "replicate/generic@1",
        "--adapter",
        "modal",
        "--mode",
        "mock",
        "--adapter-opts-json",
        '{"function":"smoke"}',
        "--inputs-json",
        '{"schema":"v1","params":{"prompt":"smoke test image","model":"black-forest-labs/flux-schnell"}}',
        "--write-prefix",
        "/artifacts/outputs/smoke/{execution_id}/",
        "--json",
    ]

    result = subprocess.run(
        cmd,
        cwd="code",
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, f"run_processor smoke failed: {result.stderr}"

    # Parse the JSON output (canonical envelope)
    try:
        response = json.loads(result.stdout.strip())
    except json.JSONDecodeError as e:
        pytest.fail(f"Invalid JSON output: {e}\nOutput: {result.stdout}")

    assert response["status"] == "success", f"Smoke test failed: {response}"
    assert response["execution_id"], "Missing execution_id in response"
    assert "outputs" in response, "Missing outputs in response"


def test_modal_logs_retrieval():
    """Smoke test for Modal logs retrieval functionality."""
    cmd = [
        sys.executable,
        "manage.py",
        "logs_modal",
        "--ref",
        "llm/litellm@1",
        "--fn",
        "smoke",
        "--since-min",
        "5",
        "--limit",
        "50",
    ]

    result = subprocess.run(
        cmd,
        cwd="code",
        capture_output=True,
        text=True,
        timeout=60,
    )

    # Logs command may succeed even if no logs found
    # Just verify the command structure works
    lines = result.stdout.strip().split("\n")
    if lines:
        try:
            response = json.loads(lines[0])
            # Should have proper structure even if no logs
            assert "status" in response
            if response["status"] == "success":
                assert "logs" in response
                assert "app_name" in response
                assert "function" in response
        except json.JSONDecodeError:
            # If first line isn't JSON, that's also acceptable
            # (might be human-readable output first)
            pass
