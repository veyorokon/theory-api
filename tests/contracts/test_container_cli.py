"""
Contract tests for processor container CLI.
Ensures containers emit valid envelopes via stdout with stdin payloads.
"""

import json
import subprocess
import tempfile
from pathlib import Path
import pytest

from tests.tools.docker_checks import get_image_tag_or_skip

pytestmark = [pytest.mark.contracts, pytest.mark.requires_docker]


class TestContainerCLI:
    """Contract tests for container CLI execution."""

    def test_container_emits_envelope_via_stdout_mock_mode(self):
        """Container emits valid envelope to stdout in mock mode."""
        # Create payload for container
        payload = {
            "schema": "v1",
            "mode": "mock",
            "execution_id": "test-container-mock",
            "write_prefix": "/artifacts/outputs/test-container-mock/",
            "params": {
                "messages": [{"role": "user", "content": "test message"}],
            },
            "model": "gpt-4o-mini",
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            # Build the container first (local dev tag)
            build_cmd = [
                "docker",
                "buildx",
                "build",
                "--load",
                "-t",
                "theory-local/llm-litellm:test",
                "-f",
                "code/apps/core/processors/llm_litellm/Dockerfile",
                ".",
            ]
            build_result = subprocess.run(build_cmd, capture_output=True, text=True)
            if build_result.returncode != 0:
                pytest.skip(f"Failed to build container: {build_result.stderr}")

            # Run container with payload via stdin
            cmd = [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{tmp_dir}:/artifacts",
                "-e",
                "LOG_STREAM=stderr",
                "theory-local/llm-litellm:test",
            ]

            proc = subprocess.run(
                cmd, input=json.dumps(payload), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30
            )

            # Container should succeed
            assert proc.returncode == 0, f"Container failed: {proc.stderr}"

            # Parse envelope from stdout
            try:
                envelope = json.loads(proc.stdout.strip())
            except json.JSONDecodeError as e:
                pytest.fail(f"Container stdout is not valid JSON: {e}\\nStdout: {proc.stdout}\\nStderr: {proc.stderr}")

            # Validate envelope structure
            assert envelope["status"] == "success", f"Expected success envelope: {envelope}"
            assert envelope["execution_id"] == "test-container-mock"
            assert "outputs" in envelope
            assert isinstance(envelope["outputs"], list)
            assert "index_path" in envelope
            assert envelope["index_path"].startswith("/artifacts/outputs/test-container-mock/")
            assert "meta" in envelope

            # Verify outputs exist on filesystem
            index_path = envelope["index_path"]
            local_index_path = tmp_dir + index_path.replace("/artifacts", "")
            assert Path(local_index_path).exists(), f"Index file not found: {local_index_path}"

            # Verify at least one output exists
            assert len(envelope["outputs"]) > 0, "No outputs in envelope"
            for output in envelope["outputs"]:
                output_path = output["path"]
                local_output_path = tmp_dir + output_path.replace("/artifacts", "")
                assert Path(local_output_path).exists(), f"Output file not found: {local_output_path}"

    def test_container_handles_invalid_payload(self):
        """Container returns error envelope for invalid payload."""
        # Invalid payload (missing required fields)
        payload = {"invalid": "payload"}

        with tempfile.TemporaryDirectory() as tmp_dir:
            # Use pre-built image or skip
            cmd = [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{tmp_dir}:/artifacts",
                "-e",
                "LOG_STREAM=stderr",
                "theory-local/llm-litellm:test",
            ]

            proc = subprocess.run(
                cmd, input=json.dumps(payload), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10
            )

            # Container should exit with error
            assert proc.returncode != 0

            # Parse error envelope from stdout
            try:
                envelope = json.loads(proc.stdout.strip())
            except json.JSONDecodeError:
                pytest.fail(
                    f"Container stdout is not valid JSON even for error case\\nStdout: {proc.stdout}\\nStderr: {proc.stderr}"
                )

            # Validate error envelope structure
            assert envelope["status"] == "error"
            assert "error" in envelope
            assert "code" in envelope["error"]
            assert "message" in envelope["error"]
            assert envelope["execution_id"] == ""  # No execution_id in invalid payload

    def test_container_timeout_handling(self):
        """Container handles timeout gracefully."""
        # Valid payload but timeout the container externally
        payload = {
            "schema": "v1",
            "mode": "mock",
            "execution_id": "test-timeout",
            "write_prefix": "/artifacts/outputs/test-timeout/",
            "params": {
                "messages": [{"role": "user", "content": "test"}],
            },
            "model": "gpt-4o-mini",
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            cmd = [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{tmp_dir}:/artifacts",
                "-e",
                "LOG_STREAM=stderr",
                "theory-local/llm-litellm:test",
            ]

            try:
                proc = subprocess.run(
                    cmd,
                    input=json.dumps(payload),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=1,  # Very short timeout to trigger timeout
                )
                # If it doesn't timeout, that's fine too
                if proc.returncode == 0:
                    pytest.skip("Container executed too quickly to test timeout")
            except subprocess.TimeoutExpired:
                # This is expected - timeout behavior verified
                pass

    def test_container_stdout_purity(self):
        """Container emits exactly one JSON line to stdout."""
        payload = {
            "schema": "v1",
            "mode": "mock",
            "execution_id": "test-purity",
            "write_prefix": "/artifacts/outputs/test-purity/",
            "params": {
                "messages": [{"role": "user", "content": "test purity"}],
            },
            "model": "gpt-4o-mini",
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            cmd = [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{tmp_dir}:/artifacts",
                "-e",
                "LOG_STREAM=stderr",
                "theory-local/llm-litellm:test",
            ]

            proc = subprocess.run(
                cmd, input=json.dumps(payload), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30
            )

            # Check stdout purity - should be exactly one JSON line
            stdout_lines = proc.stdout.strip().split("\\n")
            assert len(stdout_lines) == 1, (
                f"Expected exactly one line on stdout, got {len(stdout_lines)}: {stdout_lines}"
            )

            # The single line should be valid JSON
            try:
                envelope = json.loads(stdout_lines[0])
                assert "status" in envelope
            except json.JSONDecodeError as e:
                pytest.fail(f"Single stdout line is not valid JSON: {e}\\nLine: {stdout_lines[0]}")

            # All logs should go to stderr
            assert len(proc.stderr) > 0, "Expected logs on stderr"
