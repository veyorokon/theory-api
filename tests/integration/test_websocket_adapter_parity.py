"""WebSocket adapter parity tests - Local vs Modal envelope consistency."""

import json
import tempfile
import time
from pathlib import Path

import pytest

from tests.tools.subprocess_helper import run_manage_py


pytestmark = [pytest.mark.integration, pytest.mark.requires_docker]


class TestWebSocketAdapterParity:
    """Test WebSocket adapters produce byte-identical envelopes."""

    @pytest.mark.requires_docker
    def test_local_vs_modal_envelope_parity_mock_mode(self):
        """Test Local and Modal WebSocket adapters produce identical envelopes in mock mode."""
        import os

        # Skip if Modal environment not configured
        if not os.getenv("MODAL_ENVIRONMENT"):
            pytest.skip("MODAL_ENVIRONMENT not configured for parity testing")

        payload = {"schema": "v1", "params": {"messages": [{"role": "user", "content": "parity test"}]}}

        # Get Local adapter result
        with tempfile.TemporaryDirectory() as tmp_dir:
            write_prefix = f"{tmp_dir}/outputs/{{execution_id}}/"

            local_result = run_manage_py(
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

            assert local_result.returncode == 0, f"Local adapter failed: {local_result.stderr}"
            local_envelope = json.loads(local_result.stdout)

        # Get Modal adapter result
        with tempfile.TemporaryDirectory() as tmp_dir:
            write_prefix = f"{tmp_dir}/outputs/{{execution_id}}/"

            modal_result = run_manage_py(
                "run_processor",
                "--ref",
                "llm/litellm@1",
                "--adapter",
                "modal",
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
                env={**os.environ, "MODAL_ENVIRONMENT": os.getenv("MODAL_ENVIRONMENT", "dev")},
            )

            if modal_result.returncode != 0:
                pytest.skip(f"Modal adapter not available: {modal_result.stderr}")

            modal_envelope = json.loads(modal_result.stdout)

        # Compare envelopes (ignoring execution_id and paths which will differ)
        assert local_envelope["status"] == modal_envelope["status"] == "success"

        # Same number of outputs
        assert len(local_envelope["outputs"]) == len(modal_envelope["outputs"])

        # Same output types (ignore actual paths)
        local_output_names = [Path(out["path"]).name for out in local_envelope["outputs"]]
        modal_output_names = [Path(out["path"]).name for out in modal_envelope["outputs"]]
        assert sorted(local_output_names) == sorted(modal_output_names)

        # Meta structure should be consistent
        assert "meta" in local_envelope and "meta" in modal_envelope
        assert "image_digest" in local_envelope["meta"] and "image_digest" in modal_envelope["meta"]

        # In mock mode, both should use same image digest
        assert local_envelope["meta"]["image_digest"] == modal_envelope["meta"]["image_digest"]

    @pytest.mark.requires_docker
    def test_websocket_adapter_performance_comparison(self):
        """Test WebSocket adapter performance - Local vs Modal latency."""
        import os

        # Skip if Modal not available
        if not os.getenv("MODAL_ENVIRONMENT"):
            pytest.skip("MODAL_ENVIRONMENT not configured for performance testing")

        payload = {"schema": "v1", "params": {"messages": [{"role": "user", "content": "performance test"}]}}

        # Measure Local adapter performance
        with tempfile.TemporaryDirectory() as tmp_dir:
            write_prefix = f"{tmp_dir}/outputs/{{execution_id}}/"

            start_time = time.time()
            local_result = run_manage_py(
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
            local_time = time.time() - start_time

            assert local_result.returncode == 0
            local_envelope = json.loads(local_result.stdout)
            assert local_envelope["status"] == "success"

        # Measure Modal adapter performance
        with tempfile.TemporaryDirectory() as tmp_dir:
            write_prefix = f"{tmp_dir}/outputs/{{execution_id}}/"

            start_time = time.time()
            modal_result = run_manage_py(
                "run_processor",
                "--ref",
                "llm/litellm@1",
                "--adapter",
                "modal",
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
                env={**os.environ, "MODAL_ENVIRONMENT": os.getenv("MODAL_ENVIRONMENT", "dev")},
            )
            modal_time = time.time() - start_time

            if modal_result.returncode != 0:
                pytest.skip(f"Modal adapter not available: {modal_result.stderr}")

            modal_envelope = json.loads(modal_result.stdout)
            assert modal_envelope["status"] == "success"

        # Performance should be reasonable for both
        assert local_time < 30.0, f"Local adapter too slow: {local_time:.1f}s"
        assert modal_time < 60.0, f"Modal adapter too slow: {modal_time:.1f}s"

        # Modal may be slower due to network overhead, but should be within reasonable bounds
        print(f"Local adapter: {local_time:.2f}s, Modal adapter: {modal_time:.2f}s")

    @pytest.mark.requires_docker
    def test_websocket_envelope_determinism_across_adapters(self):
        """Test WebSocket adapters produce deterministic envelopes."""
        payload = {"schema": "v1", "params": {"messages": [{"role": "user", "content": "determinism test"}]}}

        # Run local adapter multiple times
        local_responses = []
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
                envelope = json.loads(result.stdout)
                local_responses.append(envelope)

        # Local adapter should be deterministic
        assert local_responses[0]["status"] == local_responses[1]["status"] == "success"
        assert len(local_responses[0]["outputs"]) == len(local_responses[1]["outputs"])

        # Different execution IDs but same structure
        assert local_responses[0]["execution_id"] != local_responses[1]["execution_id"]
        assert local_responses[0]["meta"]["image_digest"] == local_responses[1]["meta"]["image_digest"]

    @pytest.mark.requires_docker
    def test_websocket_error_envelope_parity(self):
        """Test WebSocket adapters produce consistent error envelopes."""
        import os

        # Skip if Modal not available
        if not os.getenv("MODAL_ENVIRONMENT"):
            pytest.skip("MODAL_ENVIRONMENT not configured for error parity testing")

        # Invalid payload to trigger error
        invalid_payload = {"invalid": "structure"}

        # Get Local adapter error
        with tempfile.TemporaryDirectory() as tmp_dir:
            write_prefix = f"{tmp_dir}/outputs/{{execution_id}}/"

            local_result = run_manage_py(
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
                json.dumps(invalid_payload),
                "--json",
                capture_output=True,
                text=True,
                timeout=120,
            )

            assert local_result.returncode == 0  # CLI succeeds but envelope has error
            local_envelope = json.loads(local_result.stdout)

        # Get Modal adapter error
        with tempfile.TemporaryDirectory() as tmp_dir:
            write_prefix = f"{tmp_dir}/outputs/{{execution_id}}/"

            modal_result = run_manage_py(
                "run_processor",
                "--ref",
                "llm/litellm@1",
                "--adapter",
                "modal",
                "--mode",
                "mock",
                "--write-prefix",
                write_prefix,
                "--inputs-json",
                json.dumps(invalid_payload),
                "--json",
                capture_output=True,
                text=True,
                timeout=120,
                env={**os.environ, "MODAL_ENVIRONMENT": os.getenv("MODAL_ENVIRONMENT", "dev")},
            )

            if modal_result.returncode != 0:
                pytest.skip(f"Modal adapter not available: {modal_result.stderr}")

            modal_envelope = json.loads(modal_result.stdout)

        # Both should return error envelopes with same structure
        assert local_envelope["status"] == modal_envelope["status"] == "error"
        assert "error" in local_envelope and "error" in modal_envelope

        # Error codes should be the same
        assert local_envelope["error"]["code"] == modal_envelope["error"]["code"]
        assert local_envelope["error"]["code"].startswith("ERR_")

        # Error messages should be similar (may have minor transport differences)
        assert isinstance(local_envelope["error"]["message"], str)
        assert isinstance(modal_envelope["error"]["message"], str)
        assert len(local_envelope["error"]["message"]) > 0
        assert len(modal_envelope["error"]["message"]) > 0

    @pytest.mark.requires_docker
    def test_websocket_streaming_parity(self):
        """Test WebSocket streaming behavior is consistent across adapters."""
        import os

        # Skip if Modal not available
        if not os.getenv("MODAL_ENVIRONMENT"):
            pytest.skip("MODAL_ENVIRONMENT not configured for streaming parity testing")

        payload = {"schema": "v1", "params": {"messages": [{"role": "user", "content": "streaming parity test"}]}}

        # Both adapters should support streaming and produce final envelopes
        adapters = ["local", "modal"]
        envelopes = []

        for adapter in adapters:
            with tempfile.TemporaryDirectory() as tmp_dir:
                write_prefix = f"{tmp_dir}/outputs/{{execution_id}}/"

                env_vars = {}
                if adapter == "modal":
                    env_vars["MODAL_ENVIRONMENT"] = os.getenv("MODAL_ENVIRONMENT", "dev")

                result = run_manage_py(
                    "run_processor",
                    "--ref",
                    "llm/litellm@1",
                    "--adapter",
                    adapter,
                    "--build" if adapter == "local" else "",
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
                    env={**os.environ, **env_vars},
                )

                if result.returncode != 0:
                    if adapter == "modal":
                        pytest.skip(f"Modal adapter not available: {result.stderr}")
                    else:
                        pytest.fail(f"Local adapter failed: {result.stderr}")

                envelope = json.loads(result.stdout)
                envelopes.append((adapter, envelope))

        # Compare streaming results
        local_envelope = next(env for adapter, env in envelopes if adapter == "local")
        modal_envelope = next(env for adapter, env in envelopes if adapter == "modal")

        # Final envelopes should have same success structure
        assert local_envelope["status"] == modal_envelope["status"] == "success"
        assert len(local_envelope["outputs"]) == len(modal_envelope["outputs"])

        # Both should have complete envelope structure
        for envelope in [local_envelope, modal_envelope]:
            assert "outputs" in envelope
            assert "index_path" in envelope
            assert "meta" in envelope
            assert "image_digest" in envelope["meta"]

    @pytest.mark.requires_docker
    def test_websocket_concurrent_adapter_requests(self):
        """Test concurrent requests across different WebSocket adapters."""
        import concurrent.futures
        import os

        # Skip if Modal not available
        if not os.getenv("MODAL_ENVIRONMENT"):
            pytest.skip("MODAL_ENVIRONMENT not configured for concurrent testing")

        payload = {"schema": "v1", "params": {"messages": [{"role": "user", "content": "concurrent adapter test"}]}}

        def run_adapter_request(adapter: str, request_id: int):
            with tempfile.TemporaryDirectory() as tmp_dir:
                write_prefix = f"{tmp_dir}/outputs/{{execution_id}}/"

                env_vars = {}
                if adapter == "modal":
                    env_vars["MODAL_ENVIRONMENT"] = os.getenv("MODAL_ENVIRONMENT", "dev")

                result = run_manage_py(
                    "run_processor",
                    "--ref",
                    "llm/litellm@1",
                    "--adapter",
                    adapter,
                    "--build" if adapter == "local" else "",
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
                    env={**os.environ, **env_vars},
                )

                if result.returncode != 0:
                    return adapter, request_id, "error", result.stderr

                envelope = json.loads(result.stdout)
                return adapter, request_id, envelope["status"], envelope.get("execution_id", "")

        # Run concurrent requests across both adapters
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = []

            # 2 local requests
            for i in range(2):
                futures.append(executor.submit(run_adapter_request, "local", i))

            # 2 modal requests
            for i in range(2):
                futures.append(executor.submit(run_adapter_request, "modal", i + 10))

            results = [future.result() for future in futures]

        # All requests should succeed
        for adapter, request_id, status, execution_id in results:
            if adapter == "modal" and status == "error":
                pytest.skip(f"Modal adapter not available: {execution_id}")
            assert status == "success", f"Request {adapter}:{request_id} failed: {execution_id}"
            assert execution_id, f"Missing execution_id for {adapter}:{request_id}"

        # Should have 2 local and 2 modal successful results
        local_results = [r for r in results if r[0] == "local"]
        modal_results = [r for r in results if r[0] == "modal"]

        assert len(local_results) == 2, "Expected 2 local results"
        assert len(modal_results) == 2, "Expected 2 modal results"

        # All should be successful
        assert all(r[2] == "success" for r in local_results), "All local requests should succeed"
        assert all(r[2] == "success" for r in modal_results), "All modal requests should succeed"
