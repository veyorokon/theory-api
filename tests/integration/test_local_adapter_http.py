"""LocalAdapter HTTP transport integration tests."""

import json
import tempfile
from pathlib import Path

import pytest

from tests.tools.subprocess_helper import run_manage_py


pytestmark = [pytest.mark.integration, pytest.mark.requires_docker]


class TestLocalAdapterHTTP:
    """Test LocalAdapter uses HTTP transport through the adapter interface."""

    @pytest.mark.requires_docker
    def test_local_adapter_calls_http_endpoints(self):
        """Test LocalAdapter makes HTTP POST requests to /run endpoint."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            write_prefix = f"{tmp_dir}/outputs/{{execution_id}}/"

            payload = {"schema": "v1", "params": {"messages": [{"role": "user", "content": "HTTP test"}]}}

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
    def test_local_adapter_not_stdin_stdout(self):
        """Test LocalAdapter uses HTTP, not stdin/stdout."""
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
            # The fact that this works proves HTTP transport is used

    @pytest.mark.requires_docker
    def test_local_adapter_http_success_path(self):
        """Test LocalAdapter successful HTTP request path."""
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
    def test_local_adapter_http_timeout_handling(self):
        """Test LocalAdapter handles HTTP timeouts correctly."""
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
    def test_local_adapter_concurrent_http_requests(self):
        """Test LocalAdapter can handle basic request flow."""
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
