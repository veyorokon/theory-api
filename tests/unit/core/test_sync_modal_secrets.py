"""
Unit tests for sync_modal_secrets management command.

Tests the command's behavior for secret syncing from environment variables to Modal.
"""

import json
import os
import subprocess
from pathlib import Path
from unittest import mock

import pytest


@pytest.mark.unit
def test_sync_modal_secrets_dry_run_with_secrets(monkeypatch):
    """Test sync_modal_secrets command dry-run mode with secrets present."""
    # Set up environment
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "backend.settings.unittest")
    monkeypatch.setenv("MODAL_ENVIRONMENT", "dev")

    # Provide dummy values for registry secrets
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test123")
    monkeypatch.setenv("REPLICATE_API_TOKEN", "r8_test123")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ant_test123")

    # Mock the registry scanning to return known secrets
    with mock.patch("apps.core.modalctl.find_required_secrets_from_registry") as mock_find:
        mock_find.return_value = {"OPENAI_API_KEY", "REPLICATE_API_TOKEN"}

        proc = subprocess.run(
            ["python", "manage.py", "sync_modal_secrets", "--env", "dev", "--registry-scan", "true"],
            cwd=str(Path(__file__).resolve().parents[3] / "code"),
            capture_output=True,
            text=True,
        )

    assert proc.returncode == 0, f"Command failed: {proc.stderr}"

    # Should output results to stdout
    output_lines = [line for line in proc.stdout.strip().split("\n") if line]
    assert len(output_lines) >= 1

    # Find the JSON output line (last line should be JSON result)
    json_line = None
    for line in reversed(output_lines):
        try:
            json_line = json.loads(line)
            break
        except json.JSONDecodeError:
            continue

    assert json_line is not None, f"No JSON output found in: {proc.stdout}"
    assert json_line["status"] == "success"
    assert json_line["env"] == "dev"


@pytest.mark.unit
def test_sync_modal_secrets_missing_required_secret_staging(monkeypatch):
    """Test sync_modal_secrets fails in staging when required secrets are missing."""
    # Create clean environment with only required plumbing vars
    clean_env = {
        "DJANGO_SETTINGS_MODULE": "backend.settings.unittest",
        "MODAL_ENVIRONMENT": "staging",
        "PYTHONPATH": ".",
        "PATH": os.environ.get("PATH", ""),
        # Only provide one secret, missing another
        "OPENAI_API_KEY": "sk-test123",
        # REPLICATE_API_TOKEN intentionally missing
    }

    # Mock the registry scanning to return both secrets as required
    with mock.patch("apps.core.modalctl.find_required_secrets_from_registry") as mock_find:
        mock_find.return_value = {"OPENAI_API_KEY", "REPLICATE_API_TOKEN"}

        proc = subprocess.run(
            ["python", "manage.py", "sync_modal_secrets", "--env", "staging", "--registry-scan", "true"],
            cwd=str(Path(__file__).resolve().parents[3] / "code"),
            capture_output=True,
            text=True,
            env=clean_env,
        )

    # Should fail with exit code 1 in staging/main when secrets missing
    assert proc.returncode == 1, f"Expected failure but got: {proc.stdout}"

    # Should have error output
    assert "REPLICATE_API_TOKEN" in proc.stderr or "REPLICATE_API_TOKEN" in proc.stdout


@pytest.mark.unit
def test_sync_modal_secrets_no_registry_secrets(monkeypatch):
    """Test sync_modal_secrets when no secrets are found in registry."""
    # Create clean environment with no secrets
    clean_env = {
        "DJANGO_SETTINGS_MODULE": "backend.settings.unittest",
        "MODAL_ENVIRONMENT": "dev",
        "PYTHONPATH": ".",
        "PATH": os.environ.get("PATH", ""),
        # No secrets in environment
    }

    # Mock registry scanning to return no secrets
    with mock.patch("apps.core.modalctl.find_required_secrets_from_registry") as mock_find:
        mock_find.return_value = set()

        proc = subprocess.run(
            ["python", "manage.py", "sync_modal_secrets", "--env", "dev", "--registry-scan", "true"],
            cwd=str(Path(__file__).resolve().parents[3] / "code"),
            capture_output=True,
            text=True,
            env=clean_env,
        )

    assert proc.returncode == 0, f"Command failed: {proc.stderr}"

    # Should contain success message about no secrets
    assert "No secrets to sync" in proc.stdout or "No secrets" in proc.stdout


@pytest.mark.unit
def test_sync_modal_secrets_explicit_secret_list(monkeypatch):
    """Test sync_modal_secrets with explicit --secrets parameter."""
    # Set up environment
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "backend.settings.unittest")
    monkeypatch.setenv("MODAL_ENVIRONMENT", "dev")
    monkeypatch.setenv("TEST_SECRET", "test_value")

    proc = subprocess.run(
        ["python", "manage.py", "sync_modal_secrets", "--env", "dev", "--secrets", "TEST_SECRET"],
        cwd=str(Path(__file__).resolve().parents[3] / "code"),
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, f"Command failed: {proc.stderr}"

    # Should process the explicitly provided secret
    assert "TEST_SECRET" in proc.stdout
