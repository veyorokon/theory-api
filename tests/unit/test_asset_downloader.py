# tests/unit/test_asset_downloader.py
"""
Unit tests for asset downloader with SSRF protection and resource limits.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import io

from libs.runtime_common.asset_downloader import (
    AssetDownloadConfig,
    AssetDownloadError,
    SSRFProtectionError,
    ResourceLimitError,
    download_asset,
    _validate_url_safety,
)


class TestAssetDownloadConfig:
    """Test AssetDownloadConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = AssetDownloadConfig()
        assert config.enabled is False
        assert config.timeout_s == 30
        assert config.max_bytes == 50 * 1024 * 1024
        assert config.chunk_size == 64 * 1024
        assert config.allowed_schemes == ("http", "https")
        assert "127.0.0.0/8" in config.blocked_networks
        assert config.user_agent == "Theory-AssetDownloader/1.0"

    def test_custom_config(self):
        """Test custom configuration values."""
        config = AssetDownloadConfig(
            enabled=True,
            timeout_s=60,
            max_bytes=100 * 1024 * 1024,
            allowed_schemes=("https",),
        )
        assert config.enabled is True
        assert config.timeout_s == 60
        assert config.max_bytes == 100 * 1024 * 1024
        assert config.allowed_schemes == ("https",)


class TestSSRFProtection:
    """Test SSRF protection validation."""

    def test_validate_valid_https_url(self):
        """Test validation of valid HTTPS URL."""
        config = AssetDownloadConfig(allowed_schemes=("https",))

        with patch("socket.getaddrinfo") as mock_getaddrinfo:
            mock_getaddrinfo.return_value = [(None, None, None, None, ("1.2.3.4", None))]

            # Should not raise
            _validate_url_safety("https://example.com/image.png", config)

    def test_validate_blocked_scheme(self):
        """Test blocking of disallowed schemes."""
        config = AssetDownloadConfig(allowed_schemes=("https",))

        with pytest.raises(SSRFProtectionError, match="Scheme 'http' not in allowed schemes"):
            _validate_url_safety("http://example.com/image.png", config)

        with pytest.raises(SSRFProtectionError, match="Scheme 'ftp' not in allowed schemes"):
            _validate_url_safety("ftp://example.com/file.txt", config)

    def test_validate_missing_hostname(self):
        """Test blocking of URLs without hostname."""
        config = AssetDownloadConfig()

        with pytest.raises(SSRFProtectionError, match="URL missing hostname"):
            _validate_url_safety("https:///path", config)

    def test_validate_localhost_blocked(self):
        """Test blocking of localhost addresses."""
        config = AssetDownloadConfig()

        with patch("socket.getaddrinfo") as mock_getaddrinfo:
            mock_getaddrinfo.return_value = [(None, None, None, None, ("127.0.0.1", None))]

            with pytest.raises(SSRFProtectionError, match="IP 127.0.0.1 is in blocked network"):
                _validate_url_safety("https://localhost/image.png", config)

    def test_validate_private_networks_blocked(self):
        """Test blocking of private network addresses."""
        config = AssetDownloadConfig()

        test_cases = [
            ("10.0.0.1", "10.0.0.0/8"),
            ("172.16.0.1", "172.16.0.0/12"),
            ("192.168.1.1", "192.168.0.0/16"),
        ]

        for ip, network in test_cases:
            with patch("socket.getaddrinfo") as mock_getaddrinfo:
                mock_getaddrinfo.return_value = [(None, None, None, None, (ip, None))]

                with pytest.raises(SSRFProtectionError, match=f"IP {ip} is in blocked network {network}"):
                    _validate_url_safety("https://private.example.com/", config)

    def test_validate_dns_resolution_failure(self):
        """Test handling of DNS resolution failures."""
        config = AssetDownloadConfig()

        with patch("socket.getaddrinfo") as mock_getaddrinfo:
            import socket

            mock_getaddrinfo.side_effect = socket.gaierror("Name resolution failed")

            with pytest.raises(SSRFProtectionError, match="Cannot resolve hostname"):
                _validate_url_safety("https://nonexistent.example.com/", config)


class TestResourceLimits:
    """Test resource limit enforcement."""

    @patch("libs.runtime_common.asset_downloader.requests")
    def test_disabled_download_returns_empty(self, mock_requests):
        """Test that disabled downloads return empty content."""
        config = AssetDownloadConfig(enabled=False)

        content, content_type = download_asset("https://example.com/image.png", config)

        assert content == b""
        assert content_type is None
        mock_requests.get.assert_not_called()

    @patch("libs.runtime_common.asset_downloader.requests")
    @patch("libs.runtime_common.asset_downloader._validate_url_safety")
    def test_successful_download(self, mock_validate, mock_requests):
        """Test successful asset download."""
        config = AssetDownloadConfig(enabled=True)

        # Mock response
        mock_response = Mock()
        mock_response.headers = {"Content-Type": "image/png"}
        mock_response.iter_content.return_value = [b"chunk1", b"chunk2"]
        mock_requests.get.return_value.__enter__.return_value = mock_response

        content, content_type = download_asset("https://example.com/image.png", config)

        assert content == b"chunk1chunk2"
        assert content_type == "image/png"
        mock_validate.assert_called_once()
        mock_requests.get.assert_called_once()

    def test_size_limit_exceeded(self):
        """Test that size limits are enforced."""
        config = AssetDownloadConfig(enabled=True, max_bytes=10)

        with (
            patch("libs.runtime_common.asset_downloader._validate_url_safety"),
            patch("libs.runtime_common.asset_downloader.requests") as mock_requests,
        ):
            # Mock response with large content
            mock_response = Mock()
            mock_response.headers = {"Content-Type": "image/png"}
            mock_response.iter_content.return_value = [b"x" * 15]  # Exceeds 10 byte limit
            mock_requests.get.return_value.__enter__.return_value = mock_response

            with pytest.raises(ResourceLimitError, match="Asset too large"):
                download_asset("https://example.com/large.png", config)

    def test_timeout_handling(self):
        """Test timeout handling."""
        config = AssetDownloadConfig(enabled=True, timeout_s=5)

        with (
            patch("libs.runtime_common.asset_downloader._validate_url_safety"),
            patch("libs.runtime_common.asset_downloader.requests") as mock_requests,
        ):
            # Mock timeout exception
            import requests

            mock_requests.get.side_effect = requests.exceptions.Timeout("Timeout")
            mock_requests.exceptions = requests.exceptions

            with pytest.raises(ResourceLimitError, match="Download timeout"):
                download_asset("https://example.com/slow.png", config)

    def test_http_error_handling(self):
        """Test HTTP error handling."""
        config = AssetDownloadConfig(enabled=True)

        with (
            patch("libs.runtime_common.asset_downloader._validate_url_safety"),
            patch("libs.runtime_common.asset_downloader.requests") as mock_requests,
        ):
            # Mock HTTP error
            import requests

            mock_requests.get.side_effect = requests.exceptions.HTTPError("404 Not Found")
            mock_requests.exceptions = requests.exceptions

            with pytest.raises(AssetDownloadError, match="HTTP request failed"):
                download_asset("https://example.com/missing.png", config)

    def test_requests_not_available(self):
        """Test handling when requests library is not available."""
        config = AssetDownloadConfig(enabled=True)

        with (
            patch("libs.runtime_common.asset_downloader._validate_url_safety"),
            patch("libs.runtime_common.asset_downloader.requests", None),
        ):
            with pytest.raises(AssetDownloadError, match="requests library not available"):
                download_asset("https://example.com/image.png", config)


class TestDownloadHeaders:
    """Test HTTP headers and user agent."""

    def test_user_agent_header(self):
        """Test that User-Agent header is set correctly."""
        config = AssetDownloadConfig(enabled=True, user_agent="Custom-Agent/1.0")

        with (
            patch("libs.runtime_common.asset_downloader._validate_url_safety"),
            patch("libs.runtime_common.asset_downloader.requests") as mock_requests,
        ):
            mock_response = Mock()
            mock_response.headers = {}
            mock_response.iter_content.return_value = [b"data"]
            mock_requests.get.return_value.__enter__.return_value = mock_response

            download_asset("https://example.com/image.png", config)

            # Verify headers were passed correctly
            call_args = mock_requests.get.call_args
            headers = call_args[1]["headers"]
            assert headers["User-Agent"] == "Custom-Agent/1.0"
            assert headers["Accept"] == "*/*"

    def test_request_parameters(self):
        """Test that request parameters are set correctly."""
        config = AssetDownloadConfig(enabled=True, timeout_s=45)

        with (
            patch("libs.runtime_common.asset_downloader._validate_url_safety"),
            patch("libs.runtime_common.asset_downloader.requests") as mock_requests,
        ):
            mock_response = Mock()
            mock_response.headers = {}
            mock_response.iter_content.return_value = [b"data"]
            mock_requests.get.return_value.__enter__.return_value = mock_response

            download_asset("https://example.com/image.png", config)

            # Verify request parameters
            call_args = mock_requests.get.call_args
            assert call_args[1]["stream"] is True
            assert call_args[1]["timeout"] == 45
            assert call_args[1]["allow_redirects"] is True


@pytest.mark.integration
class TestAssetDownloaderIntegration:
    """Integration tests with real HTTP requests (marked for integration test runs)."""

    def test_download_real_image(self):
        """Test downloading a real image (requires network)."""
        # This test would only run in integration test environment
        # and would use a test server with known assets
        pytest.skip("Integration test - requires test server setup")

    def test_ssrf_protection_real_dns(self):
        """Test SSRF protection with real DNS resolution."""
        # This test would verify that localhost and private IPs are actually blocked
        pytest.skip("Integration test - requires network access")
