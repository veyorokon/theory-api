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
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            out_dir = tmp_path / "out"
            out_dir.mkdir(parents=True)

            # Prepare inputs
            inputs = {
                "schema": "replicate-v1",
                "model": "owner/model:1",
                "params": {"prompt": "ping", "seed": 0},
                "outputs": [{"name": "primary", "type": "text", "ext": "txt"}],
            }
            inputs_path = tmp_path / "inputs.json"
            inputs_path.write_text(json.dumps(inputs), encoding="utf-8")

            # Force mock mode (no network)
            import os

            env = os.environ.copy()
            env["CI"] = "true"
            env["PYTHONPATH"] = "."

            # Execute processor
            cmd = [
                sys.executable,
                "apps/core/processors/replicate_generic/main.py",
                "--inputs",
                str(inputs_path),
                "--write-prefix",
                str(out_dir),
                "--execution-id",
                "test-exec",
            ]

            result = subprocess.run(cmd, env=env, capture_output=True, text=True, cwd=".")

            # Verify success
            assert result.returncode == 0, f"Command failed: {result.stderr}"

            # Verify outputs exist
            assert (out_dir / "outputs.json").exists()
            assert (out_dir / "receipt.json").exists()
            assert (out_dir / "response.json").exists()

            # Verify outputs.json structure
            outputs_data = json.loads((out_dir / "outputs.json").read_text())
            assert "outputs" in outputs_data
            assert isinstance(outputs_data["outputs"], list)

            # Verify receipt structure
            receipt_data = json.loads((out_dir / "receipt.json").read_text())
            assert receipt_data["execution_id"] == "test-exec"
            assert "processor_info" in receipt_data
            assert "replicate" in receipt_data["processor_info"]
            assert receipt_data["extra"].get("provider") in ["mock", "replicate"]
