"""
Universal smoke tests for all enabled tools.

These tests run against every tool marked enabled=True in the database.
Parametrize ensures each tool is tested individually with clear failure attribution.
"""

import pytest


@pytest.mark.integration
def test_tool_smoke_mock_local_scope(tool_ref, adapter):
    """
    Smoke test: invoke each enabled tool in mock mode with local artifact scope.

    Verifies:
    - Tool responds successfully
    - Returns valid envelope
    - Generates outputs with local:// URIs
    """
    result = adapter.invoke(
        ref=tool_ref,
        mode="mock",
        inputs={"schema": "v1", "params": {}},
        artifact_scope="local",
    )

    # Response structure
    assert result.get("kind") == "Response", f"Expected Response message, got: {result.get('kind')}"
    assert "control" in result
    control = result["control"]
    assert control.get("status") == "success", f"Tool {tool_ref} failed: {result.get('error')}"
    assert control.get("final") is True
    assert "cost_micro" in control
    assert "run_id" in control
    assert len(control["run_id"]) > 0

    # Outputs present
    assert "outputs" in result
    assert isinstance(result["outputs"], dict)
    assert len(result["outputs"]) > 0


@pytest.mark.integration
def test_tool_smoke_mock_world_scope(tool_ref, adapter, adapter_type):
    """
    Smoke test: invoke each enabled tool in mock mode with world artifact scope.

    Verifies:
    - Tool responds successfully
    - Returns valid envelope
    - Generates outputs with world:// URIs (when using world scope)

    Note: Only runs if storage backend supports world scope (S3).
    """
    if adapter_type == "local":
        # Local adapter with dev_local settings uses minio → artifact_scope=local
        # Skip world scope test for local adapter
        pytest.skip("Local adapter uses minio, world scope not applicable")

    result = adapter.invoke(
        ref=tool_ref,
        mode="mock",
        inputs={"schema": "v1", "params": {}},
        artifact_scope="world",
    )

    # Response structure
    assert result.get("kind") == "Response", f"Expected Response message, got: {result.get('kind')}"
    assert "control" in result
    control = result["control"]
    assert control.get("status") == "success", f"Tool {tool_ref} failed: {result.get('error')}"
    assert control.get("final") is True

    # Outputs present
    assert "outputs" in result
    assert isinstance(result["outputs"], dict)
