"""Unit tests for shared runtime helpers."""

import json
import tempfile
from pathlib import Path

import pytest

from libs.runtime_common.hashing import jcs_dumps, blake3_hex, inputs_hash
from libs.runtime_common.fingerprint import compose_env_fingerprint, memo_key
from libs.runtime_common.outputs import write_outputs, write_outputs_index
from libs.runtime_common.naming import content_cid8, write_text_file, write_json_file
from libs.runtime_common.receipts import write_dual_receipts, build_processor_receipt


class TestHashing:
    """Test hashing utilities."""

    def test_jcs_dumps_deterministic(self):
        """Test that JCS dumps produces deterministic output."""
        obj_a = {"b": 2, "a": 1}
        obj_b = {"a": 1, "b": 2}
        assert jcs_dumps(obj_a) == jcs_dumps(obj_b)
        assert jcs_dumps(obj_a) == '{"a":1,"b":2}'

    def test_blake3_hex(self):
        """Test BLAKE3 hex encoding."""
        result = blake3_hex(b"test")
        assert isinstance(result, str)
        assert len(result) == 64  # BLAKE3 produces 32-byte hash = 64 hex chars

    def test_inputs_hash_deterministic(self):
        """Test that inputs hash is deterministic for equivalent objects."""
        obj_a = {"schema": "test-v1", "model": "m", "params": {"b": 2, "a": 1}}
        obj_b = {"schema": "test-v1", "model": "m", "params": {"a": 1, "b": 2}}

        hash_a = inputs_hash(obj_a)
        hash_b = inputs_hash(obj_b)

        assert hash_a["hash_schema"] == "jcs-blake3-v1"
        assert hash_a["value"] == hash_b["value"]


class TestFingerprint:
    """Test fingerprint utilities."""

    def test_compose_env_fingerprint(self):
        """Test environment fingerprint composition."""
        result = compose_env_fingerprint(py="3.11", arch="x86_64", empty="", none=None)
        assert result == "arch=x86_64;py=3.11"

    def test_memo_key_deterministic(self):
        """Test memo key generation is deterministic."""
        key1 = memo_key(provider="test", model="m1", inputs_hash="abc123")
        key2 = memo_key(provider="test", model="m1", inputs_hash="abc123")
        assert key1 == key2
        assert isinstance(key1, str)
        assert len(key1) == 64  # BLAKE3 hex


class TestOutputs:
    """Test outputs utilities."""

    def test_write_outputs_and_index(self):
        """Test universal outputs writing and index generation."""
        from apps.core.integrations.types import OutputItem

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test output items
            outputs = [
                OutputItem(relpath="outputs/b.txt", bytes_=b"content b"),
                OutputItem(relpath="outputs/a.json", bytes_=b'{"key": "value"}'),
            ]

            # Write outputs using universal pattern
            paths = write_outputs(tmpdir, outputs)
            assert len(paths) == 2

            # Write index using new signature
            index_path = write_outputs_index("test-exec", tmpdir, paths)

            assert index_path.exists()
            data = json.loads(index_path.read_text())
            # Should be sorted by path
            assert len(data["outputs"]) == 2
            assert data["outputs"][0]["path"].endswith("/outputs/a.json")
            assert data["outputs"][1]["path"].endswith("/outputs/b.txt")


class TestNaming:
    """Test naming utilities."""

    def test_content_cid8(self):
        """Test 8-character content ID generation."""
        cid = content_cid8(b"test content")
        assert isinstance(cid, str)
        assert len(cid) == 8

    def test_write_text_file(self):
        """Test text file writing with content addressing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            text = "hello world"

            path = write_text_file(root, "test", 0, text, "txt")

            assert path.exists()
            assert path.read_text() == text
            assert "test-0-" in path.name
            assert path.name.endswith(".txt")

    def test_write_json_file(self):
        """Test JSON file writing with content addressing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            obj = {"key": "value"}

            path = write_json_file(root, "data", 1, obj)

            assert path.exists()
            data = json.loads(path.read_text())
            assert data == obj
            assert "data-1-" in path.name
            assert path.name.endswith(".json")


class TestReceipts:
    """Test receipt utilities."""

    def test_write_dual_receipts(self):
        """Test dual receipt writing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            receipt = {"execution_id": "test", "status": "completed"}

            result = write_dual_receipts("test-exec", f"{tmpdir}/", receipt, global_base=tmpdir)

            global_path = Path(result["global_path"])
            local_path = Path(result["local_path"])

            assert global_path.exists()
            assert local_path.exists()

            # Content should be identical
            assert global_path.read_bytes() == local_path.read_bytes()
            assert json.loads(global_path.read_text()) == receipt

    def test_build_processor_receipt(self):
        """Test processor receipt building."""
        receipt = build_processor_receipt(
            execution_id="test-exec",
            processor_ref="test/proc@1",
            schema="test-v1",
            provider="test",
            model="test-model",
            model_version="1.0",
            inputs_hash={"hash_schema": "jcs-blake3-v1", "value": "abc123"},
            memo_key="memo123",
            env_fingerprint="py=3.11;arch=x86_64",
            image_digest="sha256:abc123",
            timestamp_utc="2025-01-01T00:00:00Z",
            duration_ms=1000,
            outputs_index_path="outputs.json",
            output_cids=["cid1", "cid2"],
            stderr_tail="",
            logs_excerpt="test logs",
            warnings=["test warning"],
        )

        assert receipt["execution_id"] == "test-exec"
        assert receipt["schema"] == "test-v1"
        assert receipt["inputs_hash"]["hash_schema"] == "jcs-blake3-v1"
        assert receipt["duration_ms"] == 1000
        assert receipt["warnings"] == ["test warning"]
