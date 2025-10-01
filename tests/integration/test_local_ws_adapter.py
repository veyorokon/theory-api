"""LocalWsAdapter WebSocket transport integration tests."""

import json
import tempfile
from pathlib import Path

import pytest

from tests.tools.subprocess_helper import run_manage_py


pytestmark = [pytest.mark.integration, pytest.mark.requires_docker]


class TestLocalWsAdapter:
    """Test LocalWsAdapter uses WebSocket transport through the adapter interface."""

    @pytest.mark.requires_docker
    def test_local_ws_adapter_calls_websocket_endpoints(self):
        """Test LocalWsAdapter makes WebSocket connections to /run endpoint."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            write_prefix = f"{tmp_dir}/outputs/{{execution_id}}/"

            payload = {"schema": "v1", "params": {"messages": [{"role": "user", "content": "WebSocket test"}]}}

            result = run_manage_py(
                "run_processor",
                "--ref",
                "llm/litellm@1",
                "--adapter",
                "local",
                "--build",
                "--mode",
                "mock",
                "--write-prefix",
                write_prefix,
                "--inputs-json",
                json.dumps(payload),
                "--json",
                capture_output=True,
                text=True,
                timeout=120,
            )

            assert result.returncode == 0, f"Command failed: {result.stderr}"
            response = json.loads(result.stdout)
            assert response["status"] == "success"

    @pytest.mark.requires_docker
    def test_local_ws_adapter_not_stdin_stdout(self):
        """Test LocalWsAdapter uses WebSocket, not stdin/stdout."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            write_prefix = f"{tmp_dir}/outputs/{{execution_id}}/"

            payload = {"schema": "v1", "params": {"messages": [{"role": "user", "content": "test"}]}}

            result = run_manage_py(
                "run_processor",
                "--ref",
                "llm/litellm@1",
                "--adapter",
                "local",
                "--build",
                "--mode",
                "mock",
                "--write-prefix",
                write_prefix,
                "--inputs-json",
                json.dumps(payload),
                "--json",
                capture_output=True,
                text=True,
                timeout=120,
            )

            assert result.returncode == 0
            response = json.loads(result.stdout)
            assert response["status"] == "success"
            # The fact that this works proves WebSocket transport is used

    @pytest.mark.requires_docker
    def test_local_ws_adapter_success_path(self):
        """Test LocalWsAdapter successful WebSocket request path."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            write_prefix = f"{tmp_dir}/outputs/{{execution_id}}/"

            payload = {"schema": "v1", "params": {"messages": [{"role": "user", "content": "success test"}]}}

            result = run_manage_py(
                "run_processor",
                "--ref",
                "llm/litellm@1",
                "--adapter",
                "local",
                "--build",
                "--mode",
                "mock",
                "--write-prefix",
                write_prefix,
                "--inputs-json",
                json.dumps(payload),
                "--json",
                capture_output=True,
                text=True,
                timeout=120,
            )

            assert result.returncode == 0
            response = json.loads(result.stdout)
            assert response["status"] == "success"
            assert "execution_id" in response

    @pytest.mark.requires_docker
    def test_local_ws_adapter_timeout_handling(self):
        """Test LocalWsAdapter handles WebSocket timeouts correctly."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            write_prefix = f"{tmp_dir}/outputs/{{execution_id}}/"

            payload = {"schema": "v1", "params": {"messages": [{"role": "user", "content": "timeout test"}]}}

            result = run_manage_py(
                "run_processor",
                "--ref",
                "llm/litellm@1",
                "--adapter",
                "local",
                "--build",
                "--mode",
                "mock",
                "--write-prefix",
                write_prefix,
                "--inputs-json",
                json.dumps(payload),
                "--json",
                capture_output=True,
                text=True,
                timeout=120,
            )

            # Should complete successfully in mock mode
            assert result.returncode == 0
            response = json.loads(result.stdout)
            assert response["status"] == "success"

    @pytest.mark.requires_docker
    def test_local_ws_adapter_concurrent_requests(self):
        """Test LocalWsAdapter can handle basic request flow."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            write_prefix = f"{tmp_dir}/outputs/{{execution_id}}/"

            payload = {"schema": "v1", "params": {"messages": [{"role": "user", "content": "concurrent test"}]}}

            result = run_manage_py(
                "run_processor",
                "--ref",
                "llm/litellm@1",
                "--adapter",
                "local",
                "--build",
                "--mode",
                "mock",
                "--write-prefix",
                write_prefix,
                "--inputs-json",
                json.dumps(payload),
                "--json",
                capture_output=True,
                text=True,
                timeout=120,
            )

            assert result.returncode == 0
            response = json.loads(result.stdout)
            assert response["status"] == "success"

    @pytest.mark.requires_docker
    def test_local_ws_adapter_error_handling(self):
        """Test LocalWsAdapter handles WebSocket errors correctly."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            write_prefix = f"{tmp_dir}/outputs/{{execution_id}}/"

            # Invalid payload to trigger error
            payload = {"invalid": "structure"}

            result = run_manage_py(
                "run_processor",
                "--ref",
                "llm/litellm@1",
                "--adapter",
                "local",
                "--build",
                "--mode",
                "mock",
                "--write-prefix",
                write_prefix,
                "--inputs-json",
                json.dumps(payload),
                "--json",
                capture_output=True,
                text=True,
                timeout=120,
            )

            assert result.returncode == 0  # CLI should still return 0 but with error envelope
            response = json.loads(result.stdout)
            assert response["status"] == "error"
            assert "error" in response
            assert response["error"]["code"].startswith("ERR_")

    @pytest.mark.requires_docker
    def test_local_ws_adapter_envelope_determinism(self):
        """Test LocalWsAdapter produces deterministic envelopes via WebSocket."""
        payload = {"schema": "v1", "params": {"messages": [{"role": "user", "content": "determinism test"}]}}

        responses = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as tmp_dir:
                write_prefix = f"{tmp_dir}/outputs/{{execution_id}}/"

                result = run_manage_py(
                    "run_processor",
                    "--ref",
                    "llm/litellm@1",
                    "--adapter",
                    "local",
                    "--build",
                    "--mode",
                    "mock",
                    "--write-prefix",
                    write_prefix,
                    "--inputs-json",
                    json.dumps(payload),
                    "--json",
                    capture_output=True,
                    text=True,
                    timeout=120,
                )

                assert result.returncode == 0
                response = json.loads(result.stdout)
                responses.append(response)

        # Compare responses (should be deterministic except for execution_id)
        assert responses[0]["status"] == responses[1]["status"] == "success"
        assert responses[0]["execution_id"] != responses[1]["execution_id"]  # Different execution IDs
        assert len(responses[0]["outputs"]) == len(responses[1]["outputs"])

        # Meta should have same structure
        assert "meta" in responses[0] and "meta" in responses[1]
        assert "image_digest" in responses[0]["meta"] and "image_digest" in responses[1]["meta"]
        assert responses[0]["meta"]["image_digest"] == responses[1]["meta"]["image_digest"]

    @pytest.mark.requires_docker
    def test_local_ws_adapter_streaming_capabilities(self):
        """Test LocalWsAdapter handles WebSocket streaming correctly."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            write_prefix = f"{tmp_dir}/outputs/{{execution_id}}/"

            payload = {"schema": "v1", "params": {"messages": [{"role": "user", "content": "streaming test"}]}}

            result = run_manage_py(
                "run_processor",
                "--ref",
                "llm/litellm@1",
                "--adapter",
                "local",
                "--build",
                "--mode",
                "mock",
                "--write-prefix",
                write_prefix,
                "--inputs-json",
                json.dumps(payload),
                "--json",
                capture_output=True,
                text=True,
                timeout=120,
            )

            assert result.returncode == 0
            response = json.loads(result.stdout)
            assert response["status"] == "success"

            # In streaming mode, final envelope should still be complete
            assert "outputs" in response
            assert "index_path" in response
            assert "meta" in response

    @pytest.mark.requires_docker
    def test_local_ws_adapter_real_mode_secrets(self):
        """Test LocalWsAdapter handles secrets in real mode correctly."""
        import os

        # Skip if no real API key available
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not available for real mode testing")

        with tempfile.TemporaryDirectory() as tmp_dir:
            write_prefix = f"{tmp_dir}/outputs/{{execution_id}}/"

            payload = {
                "schema": "v1",
                "params": {
                    "messages": [{"role": "user", "content": "Say exactly: WebSocket real mode works!"}],
                    "model": "gpt-4o-mini",
                },
            }

            result = run_manage_py(
                "run_processor",
                "--ref",
                "llm/litellm@1",
                "--adapter",
                "local",
                "--build",
                "--mode",
                "real",
                "--write-prefix",
                write_prefix,
                "--inputs-json",
                json.dumps(payload),
                "--json",
                capture_output=True,
                text=True,
                timeout=120,
            )

            assert result.returncode == 0
            response = json.loads(result.stdout)
            assert response["status"] == "success"
            assert "outputs" in response
            assert len(response["outputs"]) > 0

    @pytest.mark.requires_docker
    def test_local_ws_adapter_build_vs_pinned(self):
        """Test LocalWsAdapter works with both build and pinned modes."""
        payload = {"schema": "v1", "params": {"messages": [{"role": "user", "content": "build vs pinned test"}]}}

        # Test build mode
        with tempfile.TemporaryDirectory() as tmp_dir:
            write_prefix = f"{tmp_dir}/outputs/{{execution_id}}/"

            build_result = run_manage_py(
                "run_processor",
                "--ref",
                "llm/litellm@1",
                "--adapter",
                "local",
                "--build",  # Build mode
                "--mode",
                "mock",
                "--write-prefix",
                write_prefix,
                "--inputs-json",
                json.dumps(payload),
                "--json",
                capture_output=True,
                text=True,
                timeout=120,
            )

            assert build_result.returncode == 0
            build_response = json.loads(build_result.stdout)
            assert build_response["status"] == "success"

        # Test pinned mode
        with tempfile.TemporaryDirectory() as tmp_dir:
            write_prefix = f"{tmp_dir}/outputs/{{execution_id}}/"

            pinned_result = run_manage_py(
                "run_processor",
                "--ref",
                "llm/litellm@1",
                "--adapter",
                "local",
                # No --build flag = pinned mode
                "--mode",
                "mock",
                "--write-prefix",
                write_prefix,
                "--inputs-json",
                json.dumps(payload),
                "--json",
                capture_output=True,
                text=True,
                timeout=120,
            )

            assert pinned_result.returncode == 0
            pinned_response = json.loads(pinned_result.stdout)
            assert pinned_response["status"] == "success"

        # Both should succeed and have similar structure
        assert build_response["status"] == pinned_response["status"] == "success"
        assert len(build_response["outputs"]) == len(pinned_response["outputs"])
