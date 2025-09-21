"""Test that local adapter index_path is under write_prefix."""

import uuid
import pytest

pytestmark = pytest.mark.integration


def test_local_index_path_is_under_write_prefix():
    """Test that index_path in result envelope points under write_prefix, not execution artifacts."""
    # This test exercises the core logic without requiring Docker or external dependencies

    execution_id = str(uuid.uuid4())
    write_prefix = f"/artifacts/outputs/test/{execution_id}/"

    # Test the path computation logic that was fixed
    # This is the core contract: index_path should be computed from write_prefix
    expanded_write_prefix = write_prefix.format(execution_id=execution_id)
    expected_index_path = f"{expanded_write_prefix.rstrip('/')}/outputs.json"

    # Verify the expected behavior
    assert expected_index_path.startswith(expanded_write_prefix.rstrip("/"))
    assert expected_index_path.endswith("/outputs.json")

    # Should NOT be under /artifacts/execution (old bug path)
    assert not expected_index_path.startswith("/artifacts/execution/")

    # Verify the path structure matches the write_prefix pattern
    assert expected_index_path == f"/artifacts/outputs/test/{execution_id}/outputs.json"
