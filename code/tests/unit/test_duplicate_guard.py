"""Tests for duplicate path detection."""

import pytest
from apps.core.adapters.base import guard_no_duplicates
from apps.core.errors import ERR_OUTPUT_DUPLICATE


class TestDuplicateGuard:
    """Test the duplicate path detection guard."""

    def test_no_duplicates_returns_none(self):
        """Should return None when no duplicates exist."""
        paths = ["/artifacts/a.txt", "/artifacts/b.txt", "/artifacts/c.txt"]
        result = guard_no_duplicates(paths, "test-exec-id")
        assert result is None

    def test_detects_exact_duplicate(self):
        """Should detect exact duplicate paths."""
        paths = ["/artifacts/a.txt", "/artifacts/b.txt", "/artifacts/a.txt"]
        result = guard_no_duplicates(paths, "test-exec-id")

        assert result is not None
        assert result["status"] == "error"
        assert result["execution_id"] == "test-exec-id"
        assert result["error"]["code"] == ERR_OUTPUT_DUPLICATE
        assert "/artifacts/a.txt" in result["error"]["message"]

    def test_detects_first_duplicate_only(self):
        """Should stop at the first duplicate found."""
        paths = ["/artifacts/a.txt", "/artifacts/a.txt", "/artifacts/b.txt", "/artifacts/b.txt"]
        result = guard_no_duplicates(paths, "test-exec-id")

        assert result is not None
        # Should report the first duplicate (a.txt, not b.txt)
        assert "/artifacts/a.txt" in result["error"]["message"]

    def test_empty_list_returns_none(self):
        """Should handle empty path list."""
        result = guard_no_duplicates([], "test-exec-id")
        assert result is None

    def test_single_path_returns_none(self):
        """Should handle single path."""
        result = guard_no_duplicates(["/artifacts/single.txt"], "test-exec-id")
        assert result is None
