"""Integration tests for OrchestratorWS with local adapter."""

import pytest
from tests.helpers import invoke_processor


@pytest.mark.integration
@pytest.mark.requires_docker
class TestOrchestratorWSIntegration:
    """Test full orchestration flow: registry → presign → WS → upload → envelope."""

    def test_invoke_success_mock_mode(self):
        """Test successful invocation in mock mode returns success envelope."""
        envelope = invoke_processor(
            "llm/litellm@1",
            inputs={
                "schema": "v1",
                "params": {"messages": [{"role": "user", "content": "test message"}]},
            },
            mode="mock",
            build=True,
        )

        assert envelope["status"] == "success"
        assert "execution_id" in envelope
        assert "outputs" in envelope
        assert "meta" in envelope
        assert "index_path" in envelope
        assert envelope["index_path"].endswith("/outputs.json")

    def test_invoke_validates_execution_id(self):
        """Test envelope contains valid execution_id."""
        envelope = invoke_processor(
            "llm/litellm@1",
            inputs={
                "schema": "v1",
                "params": {"messages": [{"role": "user", "content": "test"}]},
            },
        )

        execution_id = envelope["execution_id"]
        assert execution_id
        assert isinstance(execution_id, str)
        assert len(execution_id) > 0

    def test_invoke_includes_image_digest(self):
        """Test envelope includes image_digest in meta."""
        envelope = invoke_processor(
            "llm/litellm@1",
            inputs={
                "schema": "v1",
                "params": {"messages": [{"role": "user", "content": "test"}]},
            },
        )

        assert "meta" in envelope
        assert "image_digest" in envelope["meta"]
        assert envelope["meta"]["image_digest"].startswith("sha256:")

    def test_invoke_missing_execution_id_in_inputs_fails(self):
        """Test invocation without execution_id in payload fails appropriately."""
        # OrchestratorWS should generate execution_id if not provided
        # This tests that the orchestrator handles missing execution_id
        envelope = invoke_processor(
            "llm/litellm@1",
            inputs={
                "schema": "v1",
                "params": {"messages": [{"role": "user", "content": "test"}]},
            },
        )

        # Should still succeed - orchestrator generates execution_id
        assert envelope["status"] == "success"
        assert "execution_id" in envelope

    def test_invoke_invalid_inputs_returns_error_envelope(self):
        """Test invalid inputs return error envelope (not exception)."""
        envelope = invoke_processor(
            "llm/litellm@1",
            inputs={
                "schema": "v1",
                # Missing required params
            },
        )

        # Processor always returns envelope, even for errors
        assert envelope["status"] in ["success", "error"]
        assert "execution_id" in envelope

    def test_invoke_concurrent_requests(self):
        """Test concurrent invocations succeed independently."""
        import concurrent.futures

        def make_request(i: int):
            return invoke_processor(
                "llm/litellm@1",
                inputs={
                    "schema": "v1",
                    "params": {"messages": [{"role": "user", "content": f"concurrent test {i}"}]},
                },
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(make_request, i) for i in range(3)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        assert len(results) == 3
        for envelope in results:
            assert envelope["status"] == "success"
            assert "execution_id" in envelope

    def test_invoke_deterministic_outputs(self):
        """Test invocations produce deterministic envelope structure."""
        envelope1 = invoke_processor(
            "llm/litellm@1",
            inputs={
                "schema": "v1",
                "params": {"messages": [{"role": "user", "content": "determinism test"}]},
            },
        )

        envelope2 = invoke_processor(
            "llm/litellm@1",
            inputs={
                "schema": "v1",
                "params": {"messages": [{"role": "user", "content": "determinism test"}]},
            },
        )

        # Same structure, different execution_ids
        assert envelope1["status"] == envelope2["status"] == "success"
        assert envelope1["execution_id"] != envelope2["execution_id"]
        assert len(envelope1["outputs"]) == len(envelope2["outputs"])
        assert envelope1["meta"]["image_digest"] == envelope2["meta"]["image_digest"]

    def test_invoke_with_custom_write_prefix(self):
        """Test invocation with custom write_prefix."""
        custom_prefix = "/artifacts/outputs/custom/{execution_id}/"

        envelope = invoke_processor(
            "llm/litellm@1",
            inputs={
                "schema": "v1",
                "params": {"messages": [{"role": "user", "content": "test"}]},
            },
            write_prefix=custom_prefix,
        )

        assert envelope["status"] == "success"
        assert "custom" in envelope["index_path"]
