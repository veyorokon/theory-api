"""Unit tests for dual receipts functionality."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch
import pytest

from libs.runtime_common.receipts import write_dual_receipts


class TestDualReceiptsPath:
    """Test dual receipts path resolution and error handling."""

    def test_explicit_global_base(self):
        """Test explicit global_base parameter takes priority."""
        with tempfile.TemporaryDirectory() as tmpdir:
            receipt = {"execution_id": "test-001", "status": "completed"}

            result = write_dual_receipts(
                execution_id="test-001",
                write_prefix=f"{tmpdir}/outputs",
                receipt=receipt,
                global_base=f"{tmpdir}/global",
            )

            assert result["global_ok"] is True
            assert result["local_ok"] is True
            assert result["global_path"] == f"{tmpdir}/global/execution/test-001/determinism.json"
            assert result["local_path"] == f"{tmpdir}/outputs/receipt.json"

            # Verify files were written
            assert Path(result["global_path"]).exists()
            assert Path(result["local_path"]).exists()

    @patch.dict(os.environ, {"ARTIFACTS_BASE_DIR": "/custom/artifacts"})
    def test_env_var_fallback(self):
        """Test ARTIFACTS_BASE_DIR environment variable fallback."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Override env var for this test
            with patch.dict(os.environ, {"ARTIFACTS_BASE_DIR": f"{tmpdir}/env_artifacts"}):
                receipt = {"execution_id": "test-002", "status": "completed"}

                result = write_dual_receipts(execution_id="test-002", write_prefix=f"{tmpdir}/outputs", receipt=receipt)

                assert result["global_path"] == f"{tmpdir}/env_artifacts/execution/test-002/determinism.json"

    @patch.dict(os.environ, {}, clear=True)  # Clear env vars
    def test_tmpdir_fallback(self):
        """Test fallback to TMPDIR/artifacts when no other options."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"TMPDIR": tmpdir}):
                receipt = {"execution_id": "test-003", "status": "completed"}

                result = write_dual_receipts(execution_id="test-003", write_prefix=f"{tmpdir}/outputs", receipt=receipt)

                assert result["global_path"] == f"{tmpdir}/artifacts/execution/test-003/determinism.json"
                assert result["global_ok"] is True

    def test_identical_content(self):
        """Test that global and local receipts have identical content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            receipt = {
                "execution_id": "test-004",
                "status": "completed",
                "outputs": ["file1.txt", "file2.json"],
                "duration_ms": 1500,
            }

            result = write_dual_receipts(
                execution_id="test-004",
                write_prefix=f"{tmpdir}/outputs",
                receipt=receipt,
                global_base=f"{tmpdir}/global",
            )

            # Read both files and verify identical content
            global_content = json.loads(Path(result["global_path"]).read_text())
            local_content = json.loads(Path(result["local_path"]).read_text())

            assert global_content == local_content == receipt

    def test_global_write_failure_continues(self):
        """Test that global write failure doesn't crash execution."""
        with tempfile.TemporaryDirectory() as tmpdir:
            receipt = {"execution_id": "test-005", "status": "completed"}

            # Use read-only directory for global base
            readonly_dir = f"{tmpdir}/readonly"
            os.makedirs(readonly_dir)
            os.chmod(readonly_dir, 0o444)  # Read-only

            try:
                result = write_dual_receipts(
                    execution_id="test-005", write_prefix=f"{tmpdir}/outputs", receipt=receipt, global_base=readonly_dir
                )

                # Global should fail, local should succeed
                assert result["global_ok"] is False
                assert "global_error" in result
                assert result["local_ok"] is True
                assert Path(result["local_path"]).exists()
            finally:
                # Restore permissions for cleanup
                os.chmod(readonly_dir, 0o755)

    def test_local_write_failure_reported(self):
        """Test that local write failure is properly reported."""
        with tempfile.TemporaryDirectory() as tmpdir:
            receipt = {"execution_id": "test-006", "status": "completed"}

            # Use read-only directory for local prefix
            readonly_local = f"{tmpdir}/readonly_local"
            os.makedirs(readonly_local)
            os.chmod(readonly_local, 0o444)  # Read-only

            try:
                result = write_dual_receipts(
                    execution_id="test-006",
                    write_prefix=readonly_local,
                    receipt=receipt,
                    global_base=f"{tmpdir}/global",
                )

                # Global should succeed, local should fail
                assert result["global_ok"] is True
                assert result["local_ok"] is False
                assert "local_error" in result
                assert Path(result["global_path"]).exists()
            finally:
                # Restore permissions for cleanup
                os.chmod(readonly_local, 0o755)

    def test_path_stripping_behavior(self):
        """Test that paths are properly stripped of trailing slashes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            receipt = {"execution_id": "test-007", "status": "completed"}

            result = write_dual_receipts(
                execution_id="test-007",
                write_prefix=f"{tmpdir}/outputs/",  # Trailing slash
                receipt=receipt,
                global_base=f"{tmpdir}/global/",  # Trailing slash
            )

            # Paths should be properly normalized
            assert result["global_path"] == f"{tmpdir}/global/execution/test-007/determinism.json"
            assert result["local_path"] == f"{tmpdir}/outputs/receipt.json"
            assert result["global_ok"] is True
            assert result["local_ok"] is True
