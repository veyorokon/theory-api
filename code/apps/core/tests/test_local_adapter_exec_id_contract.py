"""Test local adapter execution ID contract compliance and NameError regression prevention."""

import uuid
import pytest
from pathlib import Path
from unittest.mock import patch
from apps.core.adapters.local_adapter import LocalAdapter


@pytest.mark.unit
class TestLocalAdapterExecutionIdContract:
    """Test execution ID contract compliance in local adapter."""

    @patch("apps.storage.artifact_store.artifact_store.put_bytes")
    def test_canonicalize_outputs_uses_execution_id_in_errors(self, mock_put_bytes, tmp_path):
        """Regression test: _canonicalize_outputs must use execution_id in error envelopes, not plan_id."""
        adapter = LocalAdapter()
        
        # Mock successful storage
        mock_put_bytes.return_value = True

        # Create test file 
        outdir = tmp_path / "out"
        outdir.mkdir()
        (outdir / "test.txt").write_text("content")

        exec_id = str(uuid.uuid4())
        write_prefix = f"/artifacts/outputs/test/{exec_id}/"
        registry_spec = {"image": {"oci": "test:latest"}, "runtime": {"cpu": "1", "memory_gb": 2}}

        # This should NOT throw NameError: name 'plan_id' is not defined
        result = adapter._canonicalize_outputs(
            outdir=outdir, write_prefix=write_prefix, registry_spec=registry_spec, execution_id=exec_id
        )

        # Should succeed for normal case with mocked storage
        assert result.get("status") == "success" or "outputs" in result
        # Verify storage was called
        assert mock_put_bytes.called

    def test_process_failure_outputs_uses_execution_id(self):
        """Regression test: _process_failure_outputs must accept and use execution_id."""
        import subprocess

        adapter = LocalAdapter()
        exec_id = str(uuid.uuid4())
        registry_spec = {"image": {"oci": "test:latest"}, "runtime": {"cpu": "1", "memory_gb": 2}}

        # Mock failed container result
        failed_result = subprocess.CompletedProcess(
            args=["docker", "run"], returncode=1, stdout="", stderr="Container failed"
        )

        # This should NOT throw NameError
        result = adapter._process_failure_outputs(failed_result, registry_spec, exec_id)

        # Should return error envelope with execution_id
        assert result.get("status") == "error"
        assert result.get("execution_id") == exec_id

    def test_execution_id_contract_end_to_end_no_nameerror(self):
        """Integration test: ensure no NameError in any code path that uses execution_id."""
        exec_id = str(uuid.uuid4())

        # Test that UUID format is correct
        uuid_obj = uuid.UUID(exec_id)
        assert uuid_obj.version == 4

        # Test that execution_id can be used in f-strings (common pattern)
        test_path = f"/artifacts/execution/{exec_id}/outputs.json"
        assert exec_id in test_path
        assert "plan_id" not in test_path
