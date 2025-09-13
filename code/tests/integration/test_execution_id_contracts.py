"""Test execution ID contract compliance across adapters."""

import uuid
import pytest
from apps.core.management.commands.run_processor import Command


pytestmark = pytest.mark.integration


class TestExecutionIdContracts:
    """Test execution ID generation and consistency across adapters."""

    def test_execution_id_is_uuid_and_consistent_across_adapters(self):
        """Test that all adapters use orchestrator-generated UUIDs consistently."""
        # Test with local and mock adapters (modal requires external service)
        adapters_to_test = ["local", "mock"]
        
        for adapter in adapters_to_test:
            cmd = Command()
            options = {
                "ref": "llm/litellm@1",
                "adapter": adapter,
                "inputs_json": '{"messages":[{"role":"user","content":"test"}]}',
                "write_prefix": "/artifacts/outputs/uuid-test/{execution_id}/",
                "json": True,
                "plan": None,
                "build": False,
                "adapter_opts_json": "{}",
                "save_dir": None,
                "save_first": None,
                "attachments": [],
            }
            
            result = cmd.handle(**options)
            
            # Parse result if it's JSON string
            if isinstance(result, str):
                import json
                result = json.loads(result)
            
            # Verify execution_id is present and is a valid UUID
            assert "execution_id" in result, f"Missing execution_id in {adapter} result"
            exec_id = result["execution_id"]
            
            # Verify it's a valid UUID v4
            try:
                uuid_obj = uuid.UUID(exec_id)
                assert uuid_obj.version == 4, f"Expected UUID v4, got version {uuid_obj.version}"
            except ValueError:
                pytest.fail(f"{adapter} adapter returned invalid UUID: {exec_id}")
            
            # Verify write_prefix contains the UUID (not hardcoded values)
            if "outputs" in result and result["outputs"]:
                first_output_path = result["outputs"][0]["path"]
                assert exec_id in first_output_path, f"Execution ID {exec_id} not found in output path {first_output_path}"
                assert "local" not in first_output_path, f"Found hardcoded 'local' in path: {first_output_path}"

    def test_execution_id_uniqueness_across_concurrent_runs(self):
        """Test that concurrent runs generate unique execution IDs."""
        cmd = Command()
        options = {
            "ref": "llm/litellm@1", 
            "adapter": "local",
            "inputs_json": '{"messages":[{"role":"user","content":"concurrent test"}]}',
            "write_prefix": "/artifacts/outputs/concurrent/{execution_id}/",
            "json": True,
            "plan": None,
            "build": False,
            "adapter_opts_json": "{}",
            "save_dir": None,
            "save_first": None,
            "attachments": [],
        }
        
        # Run twice and verify different execution IDs
        result1 = cmd.handle(**options)
        result2 = cmd.handle(**options)
        
        # Parse results
        if isinstance(result1, str):
            import json
            result1 = json.loads(result1)
            result2 = json.loads(result2)
        
        exec_id1 = result1["execution_id"] 
        exec_id2 = result2["execution_id"]
        
        assert exec_id1 != exec_id2, f"Expected unique execution IDs, got duplicate: {exec_id1}"
        assert exec_id1 != "local", "Execution ID should not be hardcoded 'local'"
        assert exec_id2 != "local", "Execution ID should not be hardcoded 'local'"