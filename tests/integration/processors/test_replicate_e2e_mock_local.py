"""Integration tests for replicate processor E2E with mock runner."""

import json
import pytest
from tests.tools.runner import run_cli, parse_stdout_json_or_fail


pytestmark = [pytest.mark.integration, pytest.mark.requires_docker]


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
        args = [
            "run_processor",
            "--ref",
            "replicate/generic@1",
            "--adapter",
            "local",
            "--mode",
            "mock",
            "--write-prefix",
            "/artifacts/outputs/replicate-e2e-test/{execution_id}/",
            "--inputs-json",
            json.dumps(inputs),
            "--json",
        ]

        env = {"CI": "true", "LOG_STREAM": "stderr"}

        result = run_cli(args, env=env)
        response = parse_stdout_json_or_fail(result)
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
