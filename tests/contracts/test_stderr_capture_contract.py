"""
Contract tests for stderr capture in subprocess execution.
Ensures all adapters capture complete stderr/stdout with bounded tails.
"""

import json
import tempfile
from pathlib import Path

import pytest

from libs.runtime_common.proc import run_cmd, build_error_message


class TestStderrCaptureContract:
    """Contract tests for bulletproof stderr/stdout capture."""

    def test_failing_process_with_stderr_captured(self):
        """Failing process writes to stderr → captured in bounded tail."""
        # Create a simple failing script
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("""
import sys
print("CRITICAL_ERROR: missing api key", file=sys.stderr)
print("Additional context line", file=sys.stderr)
sys.exit(2)
""")
            script_path = f.name

        try:
            rc, stdout, stderr, elapsed = run_cmd(["python", script_path], timeout_s=10)

            # Contract assertions
            assert rc == 2
            assert "CRITICAL_ERROR: missing api key" in stderr
            assert "Additional context line" in stderr
            assert stdout == ""  # No stdout expected
            assert elapsed > 0

            # Error message contract
            error_msg, meta = build_error_message(rc, stdout, stderr, elapsed)
            assert "Process failed with exit code 2" in error_msg
            assert "STDERR:\nCRITICAL_ERROR: missing api key" in error_msg
            assert meta["stderr_sha256"] is not None
            assert meta["elapsed_ms"] == elapsed

        finally:
            Path(script_path).unlink()

    def test_whitespace_only_stderr_detected(self):
        """Process writes only whitespace to stderr → detected and reported."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("""
import sys
print("   \\n  \\t  \\n   ", file=sys.stderr)  # whitespace only
sys.exit(1)
""")
            script_path = f.name

        try:
            rc, stdout, stderr, elapsed = run_cmd(["python", script_path], timeout_s=10)

            # Contract assertions
            assert rc == 1
            assert stderr.strip() == ""  # Only whitespace
            assert len(stderr) > 0  # But not empty

            # Error message contract
            error_msg, meta = build_error_message(rc, stdout, stderr, elapsed)
            assert "Process failed with exit code 1" in error_msg
            assert "STDERR (whitespace-only):" in error_msg
            assert f"{len(stderr)} chars" in error_msg

        finally:
            Path(script_path).unlink()

    def test_empty_stderr_handled(self):
        """Process with no stderr output → clearly reported."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("""
import sys
# No output at all
sys.exit(3)
""")
            script_path = f.name

        try:
            rc, stdout, stderr, elapsed = run_cmd(["python", script_path], timeout_s=10)

            # Contract assertions
            assert rc == 3
            assert stderr == ""
            assert stdout == ""

            # Error message contract
            error_msg, meta = build_error_message(rc, stdout, stderr, elapsed)
            assert "Process failed with exit code 3" in error_msg
            assert "STDERR: <empty>" in error_msg
            assert meta["stderr_sha256"] is None

        finally:
            Path(script_path).unlink()

    def test_successful_process_no_error_message(self):
        """Successful process → no error message needed."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("""
import sys
print("Operation completed successfully", file=sys.stderr)
print("result: success")
sys.exit(0)
""")
            script_path = f.name

        try:
            rc, stdout, stderr, elapsed = run_cmd(["python", script_path], timeout_s=10)

            # Contract assertions
            assert rc == 0
            assert "Operation completed successfully" in stderr
            assert "result: success" in stdout

            # No error message needed for success case
            # (adapters only call build_error_message on failure)

        finally:
            Path(script_path).unlink()

    def test_bounded_tail_prevents_huge_envelopes(self):
        """Large stderr output → bounded to prevent envelope bloat."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("""
import sys
# Generate large stderr output
for i in range(1000):
    print(f"Error line {i:04d}: This is a long error message with details", file=sys.stderr)
print("FINAL_ERROR: This should be in the tail", file=sys.stderr)
sys.exit(1)
""")
            script_path = f.name

        try:
            rc, stdout, stderr, elapsed = run_cmd(["python", script_path], timeout_s=10)

            # Contract assertions
            assert rc == 1
            assert "FINAL_ERROR: This should be in the tail" in stderr
            assert len(stderr) <= 8192  # Bounded by deque maxlen

            # Error message contract
            error_msg, meta = build_error_message(rc, stdout, stderr, elapsed)
            assert "FINAL_ERROR: This should be in the tail" in error_msg
            # redact_tail further limits to 4096 in error message
            assert len(error_msg) < 5000  # Reasonable envelope size

        finally:
            Path(script_path).unlink()
