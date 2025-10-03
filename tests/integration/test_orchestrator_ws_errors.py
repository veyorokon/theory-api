"""Integration tests for OrchestratorWS error handling."""

import pytest
from tests.helpers import invoke_processor


@pytest.mark.integration
@pytest.mark.requires_docker
class TestOrchestratorWSErrors:
    """Test error handling in full orchestration flow."""

    def test_invoke_nonexistent_processor_fails(self):
        """Test invoking non-existent processor fails."""
        with pytest.raises(Exception) as exc_info:
            invoke_processor(
                "nonexistent/processor@1",
                inputs={
                    "schema": "v1",
                    "params": {"messages": [{"role": "user", "content": "test"}]},
                },
            )

        # Should fail during registry load or image build
        assert "nonexistent" in str(exc_info.value).lower() or "not found" in str(exc_info.value).lower()
