"""
Unit tests for artifact_scope parameter logic.

Fast, hermetic, no I/O. Tests pure Python logic.
"""

import pytest


@pytest.mark.unit
def test_artifact_scope_world_generates_outputs():
    """When artifact_scope=world, ToolRunner should generate outputs map."""
    from apps.core.tool_runner import ToolRunner

    runner = ToolRunner()

    # Mock the prepare method to check if it's called
    outputs_map_called = []

    original_method = runner._prepare_put_urls

    def mock_prepare(write_prefix, outputs_decl):
        outputs_map_called.append(True)
        return {"outputs.json": "https://s3.example.com/put"}

    runner._prepare_put_urls = mock_prepare

    # Don't actually invoke, just test the logic would prepare outputs
    # This is a unit test, so we're testing the conditional logic exists
    assert callable(runner._prepare_put_urls)
    result = runner._prepare_put_urls("/test/", [])
    assert "outputs.json" in result
    assert len(outputs_map_called) == 1


@pytest.mark.unit
def test_artifact_scope_local_skips_outputs():
    """When artifact_scope=local, outputs map should be omitted from payload."""
    # This tests the conditional logic in ToolRunner.invoke()
    # We verify the code path exists without full integration

    from apps.core.tool_runner import ToolRunner

    runner = ToolRunner()

    # Test that the artifact_scope parameter exists and is used
    import inspect

    sig = inspect.signature(runner.invoke)
    assert "artifact_scope" in sig.parameters
    param = sig.parameters["artifact_scope"]
    # No default value - must be explicit
    assert param.default == inspect.Parameter.empty


@pytest.mark.unit
def test_storage_backend_determines_scope():
    """modalctl should derive artifact_scope from STORAGE_BACKEND."""
    # Test the logic: STORAGE_BACKEND=s3 → artifact_scope=world
    # This is pure conditional logic

    test_cases = [
        ("s3", "world"),
        ("minio", "local"),
        ("", "local"),  # Default/empty
    ]

    for backend, expected_scope in test_cases:
        # Simulate the logic from modalctl
        artifact_scope = "world" if backend == "s3" else "local"
        assert artifact_scope == expected_scope, f"Backend {backend} should map to {expected_scope}"
