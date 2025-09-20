"""Integration tests for replicate processor E2E with mock runner."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


pytestmark = pytest.mark.integration


class TestReplicateE2EMockLocal:
    """Test end-to-end replicate processor execution with mock runner."""

    def test_e2e_local_mock(self):
        """Test complete E2E execution using mock runner (no network)."""
        # Prepare inputs for replicate processor
        inputs = {"schema": "v1", "model": "owner/model:1", "params": {"prompt": "ping", "seed": 0}, "mode": "default"}

        # Force mock mode (no network)
        import os

        env = os.environ.copy()
        env["CI"] = "true"
        env["PYTHONPATH"] = "."

        # Execute processor using run_processor command (like other tests)
        cmd = [
            sys.executable,
            "manage.py",
            "run_processor",
            "--ref",
            "replicate/generic@1",
            "--adapter",
            "local",
            "--mode",
            "smoke",
            "--write-prefix",
            "/artifacts/outputs/replicate-e2e-test/{execution_id}/",
            "--inputs-json",
            json.dumps(inputs),
            "--json",
        ]

        result = subprocess.run(cmd, env=env, capture_output=True, text=True, cwd=".")

        # Verify success
        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # Parse response
        response = json.loads(result.stdout)
        assert response["status"] == "success"
        assert "execution_id" in response
        assert "outputs" in response

        # Verify outputs structure
        outputs = response["outputs"]
        assert isinstance(outputs, list)
        assert len(outputs) > 0

        # Verify at least one output exists
        for output in outputs:
            assert "path" in output
            assert "cid" in output
            assert "size_bytes" in output
            assert "mime" in output
