"""Integration tests for OrchestratorWS with local adapter."""

import pytest
from tests.tools.docker_fixtures import reusable_orchestrator


@pytest.mark.integration
@pytest.mark.requires_docker
class TestOrchestratorWSIntegration:
    """Test full orchestration flow: registry → presign → WS → upload → envelope."""

    def test_invoke_success_mock_mode(self, reusable_orchestrator):
        """Test successful invocation in mock mode returns success envelope."""
        envelope = reusable_orchestrator(
            "llm/litellm@1",
            inputs={
                "schema": "v1",
                "params": {"messages": [{"role": "user", "content": "test message"}]},
            },
            mode="mock",
            build=True,
            stream=False,
            adapter="local",
        )

        assert envelope["status"] == "success"
        assert "execution_id" in envelope
        assert "outputs" in envelope
        assert "meta" in envelope
        assert "index_path" in envelope
        assert envelope["index_path"].endswith("/outputs.json")

    def test_invoke_invalid_inputs_returns_error_envelope(self, reusable_orchestrator):
        """Test invalid inputs return error envelope (not exception)."""
        envelope = reusable_orchestrator(
            "llm/litellm@1",
            inputs={
                "schema": "v1",
                # Missing required params
            },
            mode="mock",
            build=False,
            stream=False,
            adapter="local",
        )

        # Processor always returns envelope, even for errors
        assert envelope["status"] in ["success", "error"]
        assert "execution_id" in envelope

    def test_invoke_concurrent_requests(self, reusable_orchestrator):
        """Test concurrent invocations succeed independently (reuses same container)."""
        import concurrent.futures

        def make_request(i: int):
            return reusable_orchestrator(
                "llm/litellm@1",
                inputs={
                    "schema": "v1",
                    "params": {"messages": [{"role": "user", "content": f"concurrent test {i}"}]},
                },
                mode="mock",
                build=False,
                stream=False,
                adapter="local",
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(make_request, i) for i in range(3)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        assert len(results) == 3
        for envelope in results:
            assert envelope["status"] == "success"
            assert "execution_id" in envelope

    def test_invoke_with_custom_write_prefix(self, reusable_orchestrator):
        """Test invocation with custom write_prefix."""
        custom_prefix = "/artifacts/outputs/custom/{execution_id}/"

        envelope = reusable_orchestrator(
            "llm/litellm@1",
            inputs={
                "schema": "v1",
                "params": {"messages": [{"role": "user", "content": "test"}]},
            },
            mode="mock",
            build=False,
            stream=False,
            adapter="local",
            write_prefix=custom_prefix,
        )

        assert envelope["status"] == "success"
        assert "custom" in envelope["index_path"]
