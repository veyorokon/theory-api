# tests/unit/test_asset_system_simple.py
"""
Simplified unit tests for the asset download system.
Focuses on testing the core functionality without complex mocking.
"""

import pytest
from unittest.mock import patch
import os

from libs.runtime_common.asset_downloader import AssetDownloadConfig, SSRFProtectionError, _validate_url_safety
from libs.runtime_common.asset_naming import generate_deterministic_filename, create_asset_receipt
from libs.runtime_common.asset_policy import get_asset_policy, _get_processor_family, _detect_environment


class TestAssetDownloadConfig:
    """Test AssetDownloadConfig configuration."""

    def test_default_config(self):
        """Test default configuration values."""
        config = AssetDownloadConfig()
        assert config.enabled is False
        assert config.timeout_s == 30
        assert config.max_bytes == 50 * 1024 * 1024
        assert "127.0.0.0/8" in config.blocked_networks

    def test_custom_config(self):
        """Test custom configuration."""
        config = AssetDownloadConfig(
            enabled=True,
            max_bytes=100 * 1024 * 1024,
            timeout_s=60,
        )
        assert config.enabled is True
        assert config.max_bytes == 100 * 1024 * 1024
        assert config.timeout_s == 60


class TestSSRFBasicValidation:
    """Test basic SSRF protection functionality."""

    def test_scheme_validation(self):
        """Test URL scheme validation."""
        config = AssetDownloadConfig(allowed_schemes=("https",))

        # This should raise for disallowed scheme
        with pytest.raises(SSRFProtectionError, match="Scheme 'http' not in allowed schemes"):
            _validate_url_safety("http://example.com/image.png", config)

    def test_missing_hostname(self):
        """Test validation of URLs without hostname."""
        config = AssetDownloadConfig()

        with pytest.raises(SSRFProtectionError, match="URL missing hostname"):
            _validate_url_safety("https:///path", config)


class TestDeterministicNaming:
    """Test deterministic asset naming functionality."""

    def test_filename_generation_deterministic(self):
        """Test that filename generation is deterministic."""
        content = b"test image data"
        url = "https://example.com/image.png"
        content_type = "image/png"

        filename1, hash1 = generate_deterministic_filename(content, url, content_type)
        filename2, hash2 = generate_deterministic_filename(content, url, content_type)

        assert filename1 == filename2
        assert hash1 == hash2
        assert filename1.endswith(".png")

    def test_different_content_different_hash(self):
        """Test that different content produces different hashes."""
        url = "https://example.com/image.png"
        content_type = "image/png"

        filename1, hash1 = generate_deterministic_filename(b"content1", url, content_type)
        filename2, hash2 = generate_deterministic_filename(b"content2", url, content_type)

        assert filename1 != filename2
        assert hash1 != hash2

    def test_source_hint_in_filename(self):
        """Test that source domain hint appears in filename."""
        content = b"test data"
        url = "https://replicate.delivery/path/image.webp"
        content_type = "image/webp"

        filename, _ = generate_deterministic_filename(content, url, content_type, include_source_hint=True)

        assert "replicate" in filename
        assert filename.endswith(".webp")


class TestAssetReceipts:
    """Test asset receipt creation."""

    @patch("time.strftime")
    def test_receipt_creation(self, mock_strftime):
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
        assert receipt.filename.endswith(".png")

    def test_receipt_with_metadata(self):
        """Test receipt creation with additional metadata."""
        content = b"test content"
        url = "https://example.com/file.json"
        additional_metadata = {"custom": "value", "index": "1"}

        receipt = create_asset_receipt(content, url, additional_metadata=additional_metadata)

        assert receipt.metadata["custom"] == "value"
        assert receipt.metadata["index"] == "1"
        assert receipt.metadata["source_url"] == url


class TestPolicySystem:
    """Test asset policy system."""

    def test_processor_family_extraction(self):
        """Test processor family extraction."""
        test_cases = [
            ("replicate/generic@1", "replicate"),
            ("llm/litellm@2", "llm"),
            ("custom-processor@1", "custom-processor"),
            ("simple", "simple"),
        ]

        for processor_ref, expected_family in test_cases:
            result = _get_processor_family(processor_ref)
            assert result == expected_family

    def test_environment_detection(self):
        """Test environment detection."""
        with patch.dict(os.environ, {"CI": "true"}, clear=True):
            result = _detect_environment()
            assert result == "ci"

        with patch.dict(os.environ, {"SMOKE": "true"}, clear=True):
            result = _detect_environment()
            assert result == "smoke"

        with patch.dict(os.environ, {"DJANGO_SETTINGS_MODULE": "backend.settings.unittest"}, clear=True):
            result = _detect_environment()
            assert result == "unittest"

    def test_policy_resolution(self):
        """Test basic policy resolution."""
        # Test that we can get policies for different processors
        policy_replicate = get_asset_policy("replicate/generic@1")
        policy_llm = get_asset_policy("llm/litellm@1")

        # Replicate should have larger limits
        assert policy_replicate.max_bytes >= policy_llm.max_bytes

        # In unittest environment, downloads should be disabled
        with patch.dict(os.environ, {"DJANGO_SETTINGS_MODULE": "backend.settings.unittest"}, clear=True):
            policy = get_asset_policy("replicate/generic@1")
            assert policy.enabled is False


class TestIntegration:
    """Test integration between components."""

    def test_policy_to_download_config(self):
        """Test conversion from policy to download config."""
        policy = get_asset_policy("replicate/generic@1")
        config = policy.to_download_config()

        assert isinstance(config, AssetDownloadConfig)
        assert config.enabled == policy.enabled
        assert config.max_bytes == policy.max_bytes
        assert config.timeout_s == policy.timeout_s

    def test_end_to_end_asset_naming(self):
        """Test end-to-end asset naming with realistic data."""
        # Simulate downloading an image from Replicate
        content = b"fake image data for testing"
        url = "https://replicate.delivery/xezq/QC5dzKt1C7b3L9hG7T0KvqOmkHEolEvQTQWPfWMx7HXuDcrKA/out-0.webp"
        content_type = "image/webp"

        receipt = create_asset_receipt(content, url, content_type)

        # Verify naming properties
        assert receipt.filename.endswith(".webp")
        assert "replicate" in receipt.filename
        assert len(receipt.content_hash) > 16
        assert receipt.content_size == len(content)
        assert receipt.source_url == url

        # Verify metadata
        assert receipt.metadata["source_url"] == url
        assert receipt.metadata["content_type"] == content_type
        assert "download_timestamp" in receipt.metadata
