"""Tests for dual receipt writing."""

import json
import os
import tempfile
from pathlib import Path

import pytest

from libs.runtime_common.receipts import write_dual_receipts


class TestDualReceipts:
    """Test dual receipt writing functionality."""

    def test_writes_identical_receipts(self):
        """Both receipts should be byte-for-byte identical."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            execution_id = "00000000-0000-0000-0000-000000000000"
            write_prefix = f"{tmp_dir}/artifacts/outputs/x/"
            global_base = f"{tmp_dir}/artifacts"
            receipt = {"test": True, "execution_id": execution_id, "status": "completed"}

            # Write dual receipts
            paths = write_dual_receipts(execution_id, write_prefix, receipt, global_base)

            # Read both files
            global_content = Path(paths["global_path"]).read_bytes()
            local_content = Path(paths["local_path"]).read_bytes()

            # Should be identical
            assert global_content == local_content

            # Both should deserialize to the same object
            global_obj = json.loads(global_content.decode("utf-8"))
            local_obj = json.loads(local_content.decode("utf-8"))
            assert global_obj == local_obj == receipt

    def test_creates_parent_directories(self):
        """Should create parent directories if they don't exist."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            execution_id = "test-exec-id"
            write_prefix = f"{tmp_dir}/deep/nested/path/"
            global_base = f"{tmp_dir}/artifacts"
            receipt = {"test": True}

            # Parent directories don't exist yet
            assert not os.path.exists(f"{tmp_dir}/deep")

            paths = write_dual_receipts(execution_id, write_prefix, receipt, global_base)

            # Both files should exist
            assert Path(paths["global_path"]).exists()
            assert Path(paths["local_path"]).exists()

    def test_handles_trailing_slash_in_prefix(self):
        """Should handle write_prefix with or without trailing slash."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            execution_id = "test-exec-id"
            global_base = f"{tmp_dir}/artifacts"
            receipt = {"test": True}

            # Test with trailing slash
            paths1 = write_dual_receipts(execution_id, f"{tmp_dir}/with/", receipt, global_base)

            # Test without trailing slash
            paths2 = write_dual_receipts(execution_id, f"{tmp_dir}/without", receipt, global_base)

            # Both should create receipt.json in the correct location
            assert paths1["local_path"].endswith("/with/receipt.json")
            assert paths2["local_path"].endswith("/without/receipt.json")

            # Both should exist
            assert Path(paths1["local_path"]).exists()
            assert Path(paths2["local_path"]).exists()

    def test_uses_compact_json(self):
        """Should use compact JSON format."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            execution_id = "test-exec-id"
            write_prefix = f"{tmp_dir}/test/"
            global_base = f"{tmp_dir}/artifacts"
            receipt = {"key": "value", "nested": {"a": 1, "b": 2}}

            paths = write_dual_receipts(execution_id, write_prefix, receipt, global_base)
            content = Path(paths["global_path"]).read_text(encoding="utf-8")

            # Should be compact (no extra spaces)
            assert '": "' not in content  # No space after colon
            assert '", "' not in content  # No space after comma in objects

    def test_preserves_utf8_content(self):
        """Should handle UTF-8 content correctly."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            execution_id = "test-exec-id"
            write_prefix = f"{tmp_dir}/test/"
            global_base = f"{tmp_dir}/artifacts"
            receipt = {"message": "测试 UTF-8 content", "emoji": "🎉"}

            paths = write_dual_receipts(execution_id, write_prefix, receipt, global_base)

            # Read and verify UTF-8 content
            global_obj = json.loads(Path(paths["global_path"]).read_text(encoding="utf-8"))
            local_obj = json.loads(Path(paths["local_path"]).read_text(encoding="utf-8"))

            assert global_obj["message"] == "测试 UTF-8 content"
            assert global_obj["emoji"] == "🎉"
            assert global_obj == local_obj

    def test_global_path_format(self):
        """Global path should follow the correct format."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            execution_id = "abc-123-def"
            write_prefix = f"{tmp_dir}/test/"
            global_base = f"{tmp_dir}/artifacts"
            receipt = {"test": True}

            paths = write_dual_receipts(execution_id, write_prefix, receipt, global_base)

            expected_global = f"{global_base}/execution/{execution_id}/determinism.json"
            assert paths["global_path"] == expected_global
