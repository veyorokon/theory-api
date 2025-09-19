# tests/unit/test_asset_naming.py
"""
Unit tests for deterministic asset naming and receipt generation.
"""

import pytest
from unittest.mock import patch

from libs.runtime_common.asset_naming import (
    AssetReceipt,
    determine_asset_extension,
    generate_deterministic_filename,
    create_asset_receipt,
    _compute_content_hash,
    _safe_extension_from_content_type,
    _extension_from_url,
    _sanitize_filename_part,
)


class TestAssetReceipt:
    """Test AssetReceipt dataclass."""

    def test_receipt_creation(self):
        """Test basic receipt creation."""
        receipt = AssetReceipt(
            content_hash="abc123",
            content_size=1024,
            source_url="https://example.com/image.png",
            download_timestamp="2025-01-01T00:00:00Z",
            filename="test.png",
        )

        assert receipt.content_hash == "abc123"
        assert receipt.content_size == 1024
        assert receipt.source_url == "https://example.com/image.png"
        assert receipt.filename == "test.png"
        assert receipt.metadata == {}  # Default empty dict

    def test_receipt_with_metadata(self):
        """Test receipt creation with metadata."""
        metadata = {"custom": "value", "index": "1"}
        receipt = AssetReceipt(
            content_hash="def456",
            content_size=2048,
            source_url="https://example.com/data.json",
            download_timestamp="2025-01-01T12:00:00Z",
            filename="data.json",
            metadata=metadata,
        )

        assert receipt.metadata == metadata


class TestContentHashing:
    """Test content hashing functionality."""

    def test_content_hash_deterministic(self):
        """Test that content hashing is deterministic."""
        content = b"test content for hashing"

        hash1 = _compute_content_hash(content)
        hash2 = _compute_content_hash(content)

        assert hash1 == hash2
        assert len(hash1) > 0

    def test_different_content_different_hash(self):
        """Test that different content produces different hashes."""
        content1 = b"content one"
        content2 = b"content two"

        hash1 = _compute_content_hash(content1)
        hash2 = _compute_content_hash(content2)

        assert hash1 != hash2

    def test_empty_content_hash(self):
        """Test hashing empty content."""
        content = b""
        hash_result = _compute_content_hash(content)

        assert len(hash_result) > 0


class TestExtensionDetection:
    """Test file extension detection from various sources."""

    def test_extension_from_content_type(self):
        """Test extension detection from content-type headers."""
        test_cases = [
            ("image/png", ".png"),
            ("image/jpeg", ".jpg"),
            ("image/webp", ".webp"),
            ("application/json", ".json"),
            ("text/plain", ".txt"),
            ("video/mp4", ".mp4"),
            ("audio/mpeg", ".mp3"),
            (None, ".bin"),
            ("", ".bin"),
            ("invalid/unknown", ".bin"),
        ]

        for content_type, expected in test_cases:
            result = _safe_extension_from_content_type(content_type)
            assert result == expected, f"Failed for {content_type}"

    def test_extension_from_content_type_with_charset(self):
        """Test content-type with charset parameter."""
        result = _safe_extension_from_content_type("image/png; charset=utf-8")
        assert result == ".png"

        result = _safe_extension_from_content_type("text/html; charset=utf-8; boundary=something")
        assert result == ".html"

    def test_extension_from_url(self):
        """Test extension extraction from URLs."""
        test_cases = [
            ("https://example.com/image.png", ".png"),
            ("https://example.com/data.json", ".json"),
            ("https://example.com/file.PDF", ".pdf"),  # Case insensitive
            ("https://example.com/path/file.webp", ".webp"),
            ("https://example.com/noextension", None),
            ("https://example.com/", None),
            ("https://example.com/file.toolongext", None),  # Too long
            ("https://example.com/file.123invalid", None),  # Invalid chars
        ]

        for url, expected in test_cases:
            result = _extension_from_url(url)
            assert result == expected, f"Failed for {url}"

    def test_determine_asset_extension_priority(self):
        """Test extension determination priority order."""
        # Content-type wins over URL
        result = determine_asset_extension("image/png", "https://example.com/file.jpg")
        assert result == ".png"

        # URL extension used when content-type is generic
        result = determine_asset_extension("application/octet-stream", "https://example.com/file.webp")
        assert result == ".webp"

        # Fallback to .bin when both are unavailable
        result = determine_asset_extension(None, "https://example.com/noext")
        assert result == ".bin"


class TestFilenameSanitization:
    """Test filename sanitization for cross-platform compatibility."""

    def test_sanitize_normal_filename(self):
        """Test sanitization of normal filenames."""
        result = _sanitize_filename_part("normal_file-name.ext")
        assert result == "normal_file-name.ext"

    def test_sanitize_problematic_characters(self):
        """Test removal of problematic characters."""
        test_cases = [
            ("file<name>", "file_name"),
            ("file:name", "file_name"),
            ('file"name', "file_name"),
            ("file/name\\path", "file_name_path"),
            ("file|name?", "file_name"),
            ("file*name", "file_name"),
        ]

        for input_name, expected in test_cases:
            result = _sanitize_filename_part(input_name)
            assert result == expected, f"Failed for {input_name}"

    def test_sanitize_multiple_separators(self):
        """Test consolidation of multiple separators."""
        result = _sanitize_filename_part("file___name   with    spaces")
        assert result == "file_name_with_spaces"

    def test_sanitize_edge_cases(self):
        """Test edge cases in sanitization."""
        # Empty string
        result = _sanitize_filename_part("")
        assert result == "asset"

        # Only problematic characters
        result = _sanitize_filename_part("<<<>>>")
        assert result == "asset"

        # Leading/trailing problematic chars
        result = _sanitize_filename_part("___file_name___")
        assert result == "file_name"

    def test_sanitize_length_limit(self):
        """Test length limiting."""
        long_name = "a" * 100
        result = _sanitize_filename_part(long_name, max_length=20)
        assert len(result) <= 20
        assert result == "a" * 20


class TestDeterministicFilenames:
    """Test deterministic filename generation."""

    def test_filename_generation_deterministic(self):
        """Test that filename generation is deterministic."""
        content = b"test image data"
        url = "https://example.com/image.png"
        content_type = "image/png"

        filename1, hash1 = generate_deterministic_filename(content, url, content_type)
        filename2, hash2 = generate_deterministic_filename(content, url, content_type)

        assert filename1 == filename2
        assert hash1 == hash2

    def test_filename_with_source_hint(self):
        """Test filename generation with source domain hint."""
        content = b"test data"
        url = "https://replicate.delivery/path/image.webp"
        content_type = "image/webp"

        filename, content_hash = generate_deterministic_filename(content, url, content_type, include_source_hint=True)

        assert "replicate" in filename
        assert filename.endswith(".webp")
        assert len(content_hash) > 16

    def test_filename_without_source_hint(self):
        """Test pure content-addressed filename generation."""
        content = b"test data"
        url = "https://example.com/file.png"
        content_type = "image/png"

        filename, content_hash = generate_deterministic_filename(content, url, content_type, include_source_hint=False)

        assert "example" not in filename
        assert filename.endswith(".png")
        assert filename.startswith(content_hash[:16])

    def test_different_content_different_filename(self):
        """Test that different content produces different filenames."""
        url = "https://example.com/image.png"
        content_type = "image/png"

        filename1, _ = generate_deterministic_filename(b"content1", url, content_type)
        filename2, _ = generate_deterministic_filename(b"content2", url, content_type)

        assert filename1 != filename2


class TestAssetReceiptCreation:
    """Test complete asset receipt creation."""

    @patch("time.strftime")
    def test_create_receipt_basic(self, mock_strftime):
        """Test basic receipt creation."""
        mock_strftime.return_value = "2025-01-01T12:00:00Z"

        content = b"test asset content"
        url = "https://example.com/asset.png"
        content_type = "image/png"

        receipt = create_asset_receipt(content, url, content_type)

        assert receipt.content_size == len(content)
        assert receipt.source_url == url
        assert receipt.content_type == content_type
        assert receipt.download_timestamp == "2025-01-01T12:00:00Z"
        assert receipt.extension == ".png"
        assert "example" in receipt.filename
        assert receipt.filename.endswith(".png")

    def test_create_receipt_with_metadata(self):
        """Test receipt creation with additional metadata."""
        content = b"test content"
        url = "https://example.com/file.json"
        content_type = "application/json"
        additional_metadata = {"custom": "value", "index": "1"}

        receipt = create_asset_receipt(content, url, content_type, additional_metadata=additional_metadata)

        # Check that additional metadata is included
        assert receipt.metadata["custom"] == "value"
        assert receipt.metadata["index"] == "1"

        # Check that standard metadata is also present
        assert receipt.metadata["source_url"] == url
        assert receipt.metadata["content_type"] == content_type
        assert "download_timestamp" in receipt.metadata

    def test_create_receipt_custom_timestamp(self):
        """Test receipt creation with custom timestamp."""
        content = b"test content"
        url = "https://example.com/file.txt"
        timestamp = "2025-06-15T14:30:00Z"

        receipt = create_asset_receipt(content, url, download_timestamp=timestamp)

        assert receipt.download_timestamp == timestamp
        assert receipt.metadata["download_timestamp"] == timestamp


class TestContentAddressing:
    """Test content-addressed naming properties."""

    def test_same_content_same_receipt(self):
        """Test that identical content produces identical receipts."""
        content = b"identical test content"
        url1 = "https://site1.com/file.png"
        url2 = "https://site2.com/different.png"
        content_type = "image/png"

        # Same content from different URLs should have same content hash
        receipt1 = create_asset_receipt(content, url1, content_type)
        receipt2 = create_asset_receipt(content, url2, content_type)

        assert receipt1.content_hash == receipt2.content_hash
        assert receipt1.content_size == receipt2.content_size
        # But filenames may differ due to source hints
        # and source URLs are definitely different
        assert receipt1.source_url != receipt2.source_url
