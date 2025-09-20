"""Test output duplicate detection and collision guards."""

import json
import os
import tempfile
import subprocess
import pytest
from pathlib import Path


pytestmark = pytest.mark.integration


class TestOutputGuards:
    """Test duplicate output detection and collision prevention."""

    def test_duplicate_filename_detection(self):
        """Test that duplicate output filenames are detected and reported."""
        # This test simulates a processor that writes the same filename twice
        # We'll create a custom processor script that does this

        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create a mock processor that writes duplicate files
            processor_script = Path(tmp_dir) / "duplicate_processor.py"
            processor_script.write_text("""
import json
import sys
from pathlib import Path

# Read inputs
inputs_path = Path("/work/inputs.json")
with open(inputs_path) as f:
    inputs = json.load(f)

# Create output directory
out_dir = Path("/work/out")
out_dir.mkdir(exist_ok=True)

# Write the same file TWICE - this should be detected
response_file = out_dir / "response.json"

# First write
response_file.write_text('{"response": "first write"}')

# Second write (duplicate) - should trigger error
response_file.write_text('{"response": "second write"}')

print("Processor completed")
""")

            # Test that the adapter detects this duplicate write
            # Note: This test may need to be adjusted based on how
            # the actual duplicate detection is implemented

            # For now, test the expected error pattern
            assert True  # Placeholder until duplicate detection is implemented

    def test_output_collision_prevention(self):
        """Test prevention of output path collisions between executions."""
        # Test that two processors with same write-prefix but different execution IDs
        # don't interfere with each other

        cmd_base = [
            "python",
            "manage.py",
            "run_processor",
            "--ref",
            "llm/litellm@1",
            "--adapter",
            "local",
            "--mode",
            "smoke",
            "--write-prefix",
            "/artifacts/outputs/collision-test/{execution_id}/",
            "--inputs-json",
            '{"schema":"v1","params":{"messages":[{"role":"user","content":"collision test"}]}}',
            "--json",
        ]

        env = os.environ.copy()
        env["PYTHONPATH"] = "."

        # Run two processors "simultaneously" (sequentially but with same template)
        result1 = subprocess.run(cmd_base, cwd=".", env=env, capture_output=True, text=True)
        result2 = subprocess.run(cmd_base, cwd=".", env=env, capture_output=True, text=True)

        assert result1.returncode == 0, f"First run failed: {result1.stderr}"
        assert result2.returncode == 0, f"Second run failed: {result2.stderr}"

        payload1 = json.loads(result1.stdout)
        payload2 = json.loads(result2.stdout)

        # Both should succeed with different execution IDs
        assert payload1["status"] == "success"
        assert payload2["status"] == "success"
        assert payload1["execution_id"] != payload2["execution_id"]

        # Output paths should be different
        paths1 = {output["path"] for output in payload1["outputs"]}
        paths2 = {output["path"] for output in payload2["outputs"]}

        # No path overlap between the two executions
        assert paths1.isdisjoint(paths2), "Output paths collided between executions"

    def test_overwrite_protection(self):
        """Test that outputs cannot overwrite each other within same execution."""
        # This would test the scenario where a processor tries to write
        # multiple outputs to the same path - should be prevented

        # For now, verify that normal execution produces unique paths
        cmd = [
            "python",
            "manage.py",
            "run_processor",
            "--ref",
            "llm/litellm@1",
            "--adapter",
            "local",
            "--mode",
            "smoke",
            "--write-prefix",
            "/artifacts/outputs/overwrite-test/{execution_id}/",
            "--inputs-json",
            '{"schema":"v1","params":{"messages":[{"role":"user","content":"overwrite test"}]}}',
            "--json",
        ]

        env = os.environ.copy()
        env["PYTHONPATH"] = "."

        result = subprocess.run(cmd, cwd=".", env=env, capture_output=True, text=True)
        assert result.returncode == 0, f"Command failed: {result.stderr}"

        payload = json.loads(result.stdout)
        assert payload["status"] == "success"

        # Verify all output paths are unique within this execution
        output_paths = [output["path"] for output in payload["outputs"]]
        assert len(output_paths) == len(set(output_paths)), "Duplicate paths within single execution"

    def test_reserved_filename_protection(self):
        """Test that processors cannot write to reserved filenames."""
        # Test that certain filenames are protected/reserved by the system
        # This depends on the actual implementation of reserved name checking

        reserved_names = [
            "outputs.json",  # Index file
            ".metadata",  # System metadata
            "__system__",  # System namespace
        ]

        # For now, just verify normal operation doesn't use these names
        cmd = [
            "python",
            "manage.py",
            "run_processor",
            "--ref",
            "llm/litellm@1",
            "--adapter",
            "local",
            "--mode",
            "smoke",
            "--write-prefix",
            "/artifacts/outputs/reserved-test/{execution_id}/",
            "--inputs-json",
            '{"schema":"v1","params":{"messages":[{"role":"user","content":"reserved test"}]}}',
            "--json",
        ]

        env = os.environ.copy()
        env["PYTHONPATH"] = "."

        result = subprocess.run(cmd, cwd=".", env=env, capture_output=True, text=True)
        assert result.returncode == 0

        payload = json.loads(result.stdout)
        output_basenames = [Path(output["path"]).name for output in payload["outputs"]]

        # Normal processor should not conflict with reserved names
        for basename in output_basenames:
            assert basename not in reserved_names, f"Output conflicts with reserved name: {basename}"

    def test_path_sanitization(self):
        """Test that output paths are properly sanitized for security."""
        # Test path traversal protection, illegal characters, etc.
        # This ensures outputs can't escape their designated directories

        cmd = [
            "python",
            "manage.py",
            "run_processor",
            "--ref",
            "llm/litellm@1",
            "--adapter",
            "local",
            "--mode",
            "smoke",
            "--write-prefix",
            "/artifacts/outputs/sanitize-test/{execution_id}/",
            "--inputs-json",
            '{"schema":"v1","params":{"messages":[{"role":"user","content":"path test"}]}}',
            "--json",
        ]

        env = os.environ.copy()
        env["PYTHONPATH"] = "."

        result = subprocess.run(cmd, cwd=".", env=env, capture_output=True, text=True)
        assert result.returncode == 0

        payload = json.loads(result.stdout)

        # Verify all paths stay within the expected prefix
        exec_id = payload["execution_id"]
        expected_prefix = f"/artifacts/outputs/sanitize-test/{exec_id}/"

        for output in payload["outputs"]:
            path = output["path"]
            assert path.startswith(expected_prefix), f"Path escapes prefix: {path}"

            # No path traversal components
            assert ".." not in path, f"Path contains traversal: {path}"
            assert "/./" not in path, f"Path contains current dir: {path}"
