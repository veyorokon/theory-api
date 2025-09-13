"""Tests for envelope helper functions."""

import json
import pytest

from apps.core.adapters.envelope import write_outputs_index


class TestOutputsIndex:
    """Test the centralized outputs index writer."""

    def test_sorts_outputs_by_path(self):
        """Outputs should be sorted by path for determinism."""
        entries = [
            {"path": "/artifacts/b.txt", "cid": "cid2", "size_bytes": 20, "mime": "text/plain"},
            {"path": "/artifacts/a.txt", "cid": "cid1", "size_bytes": 10, "mime": "text/plain"},
            {"path": "/artifacts/c.txt", "cid": "cid3", "size_bytes": 30, "mime": "text/plain"},
        ]

        index_bytes = write_outputs_index("/artifacts/execution/test/outputs.json", entries)
        index_obj = json.loads(index_bytes.decode("utf-8"))

        assert index_obj["outputs"][0]["path"] == "/artifacts/a.txt"
        assert index_obj["outputs"][1]["path"] == "/artifacts/b.txt"
        assert index_obj["outputs"][2]["path"] == "/artifacts/c.txt"

    def test_preserves_all_fields(self):
        """All fields should be preserved in the output."""
        entries = [{"path": "/artifacts/test.txt", "cid": "blake3:abc", "size_bytes": 100, "mime": "text/plain"}]

        index_bytes = write_outputs_index("/artifacts/execution/test/outputs.json", entries)
        index_obj = json.loads(index_bytes.decode("utf-8"))

        assert len(index_obj["outputs"]) == 1
        output = index_obj["outputs"][0]
        assert output["path"] == "/artifacts/test.txt"
        assert output["cid"] == "blake3:abc"
        assert output["size_bytes"] == 100
        assert output["mime"] == "text/plain"

    def test_uses_compact_json(self):
        """JSON should be compact with no extra whitespace."""
        entries = [{"path": "/artifacts/test.txt", "cid": "cid1", "size_bytes": 10, "mime": "text/plain"}]

        index_bytes = write_outputs_index("/artifacts/execution/test/outputs.json", entries)
        index_str = index_bytes.decode("utf-8")

        # Check for compact separators
        assert '", "' not in index_str  # No space after comma in arrays
        assert '": "' not in index_str  # No space after colon in objects
        assert '","' in index_str or '":"' in index_str  # Has compact separators

    def test_utf8_encoding(self):
        """Should handle UTF-8 paths correctly."""
        entries = [{"path": "/artifacts/测试.txt", "cid": "cid1", "size_bytes": 10, "mime": "text/plain"}]

        index_bytes = write_outputs_index("/artifacts/execution/test/outputs.json", entries)
        index_obj = json.loads(index_bytes.decode("utf-8"))

        assert index_obj["outputs"][0]["path"] == "/artifacts/测试.txt"
