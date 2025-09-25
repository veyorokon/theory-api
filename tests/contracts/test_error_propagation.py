"""
Contract tests for error message propagation in subprocess execution.
Ensures adapters include stderr content in main error messages.
"""

import json
import tempfile
from pathlib import Path

import pytest

from libs.runtime_common.proc import run_cmd, build_error_message


class TestErrorPropagation:
    """Contract tests for error message propagation with stderr."""

    def test_build_error_message_includes_stderr(self):
        """build_error_message includes stderr in main message, not just meta."""
        # Simulate error with stderr content
        rc = 2
        stdout = ""
        stderr = (
            "usage: processor [-h] --inputs INPUTS\nprocessor: error: the following arguments are required: --inputs"
        )
        elapsed_ms = 100

        error_msg, meta = build_error_message(rc, stdout, stderr, elapsed_ms)

        # Main message must include stderr content
        assert "Process failed with exit code 2" in error_msg
        assert "STDERR:" in error_msg
        assert "required: --inputs" in error_msg

        # Meta must include metrics
        assert meta["stderr_sha256"] is not None
        assert meta["stderr_len"] == len(stderr)
        assert meta["elapsed_ms"] == elapsed_ms

    def test_failing_processor_stderr_in_envelope(self):
        """Failing processor returns stderr in error envelope message."""
        # Create a failing processor script
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("""
import sys
import argparse

parser = argparse.ArgumentParser(prog='test_processor')
parser.add_argument('--inputs', required=True)
parser.add_argument('--write-prefix', required=True)
parser.add_argument('--execution-id', required=True)

# This will fail and print usage to stderr
args = parser.parse_args()
""")
            script_path = f.name

        try:
            # Run with missing arguments to trigger failure
            rc, stdout, stderr, elapsed = run_cmd(["python", script_path], timeout_s=10)

            # Should fail with exit code 2 (argparse error)
            assert rc == 2
            assert "required" in stderr
            assert "--inputs" in stderr

            # Build error message
            error_msg, meta = build_error_message(rc, stdout, stderr, elapsed)

            # Error message must contain stderr
            assert "Process failed with exit code 2" in error_msg
            assert "STDERR:" in error_msg
            assert "--inputs" in error_msg or "required" in error_msg

        finally:
            Path(script_path).unlink()

    def test_whitespace_stderr_in_error_message(self):
        """Whitespace-only stderr is properly indicated."""
        rc = 1
        stdout = ""
        stderr = "   \n\t  \n   "
        elapsed_ms = 50

        error_msg, meta = build_error_message(rc, stdout, stderr, elapsed_ms)

        # Should indicate whitespace-only
        assert "Process failed with exit code 1" in error_msg
        assert "STDERR (whitespace-only):" in error_msg
        assert f"{len(stderr)} chars" in error_msg

    def test_empty_stderr_in_error_message(self):
        """Empty stderr is clearly indicated."""
        rc = 1
        stdout = ""
        stderr = ""
        elapsed_ms = 50

        error_msg, meta = build_error_message(rc, stdout, stderr, elapsed_ms)

        # Should indicate empty stderr
        assert "Process failed with exit code 1" in error_msg
        assert "STDERR: <empty>" in error_msg
        assert meta["stderr_sha256"] is None

    def test_bounded_stderr_prevents_huge_messages(self):
        """Large stderr is bounded to prevent huge error messages."""
        rc = 1
        stdout = ""
        # Generate large stderr
        stderr = "\n".join(
            [f"Error line {i}: This is a very long error message with lots of details" for i in range(1000)]
        )
        stderr += "\nFINAL ERROR: This should be in the bounded tail"
        elapsed_ms = 100

        error_msg, meta = build_error_message(rc, stdout, stderr, elapsed_ms)

        # Error message should be bounded
        assert len(error_msg) < 5000  # Reasonable size
        assert "FINAL ERROR: This should be in the bounded tail" in error_msg

        # Meta should have full size info
        assert meta["stderr_len"] == len(stderr)
        assert meta["stderr_sha256"] is not None
