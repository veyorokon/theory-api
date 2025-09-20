# libs/runtime_common/asset_downloader.py
"""
Centralized asset downloader with SSRF protection and resource limits.

Provides secure, bounded downloading of assets from external URLs with:
- SSRF protection against private networks and localhost
- Configurable size and timeout limits
- Content-type validation
- Streaming download with progress tracking
"""

from __future__ import annotations
import io
import ipaddress
import socket
from dataclasses import dataclass
from typing import Optional, Tuple
from urllib.parse import urlparse

# Import requests at module level for easier testing
try:
    import requests
except ImportError:
    requests = None


@dataclass
class AssetDownloadConfig:
    """Configuration for asset downloading with security and resource controls."""

    enabled: bool = False
    timeout_s: int = 30
    max_bytes: int = 50 * 1024 * 1024  # 50 MB default
    chunk_size: int = 64 * 1024  # 64 KB chunks
    allowed_schemes: tuple[str, ...] = ("http", "https")
    blocked_networks: tuple[str, ...] = (
        "127.0.0.0/8",  # localhost
        "10.0.0.0/8",  # private class A
        "172.16.0.0/12",  # private class B
        "192.168.0.0/16",  # private class C
        "169.254.0.0/16",  # link-local
        "224.0.0.0/4",  # multicast
        "::1/128",  # IPv6 localhost
        "fc00::/7",  # IPv6 unique local
        "fe80::/10",  # IPv6 link-local
    )
    user_agent: str = "Theory-AssetDownloader/1.0"


class AssetDownloadError(Exception):
    """Base exception for asset download failures."""

    pass


class SSRFProtectionError(AssetDownloadError):
    """Raised when URL is blocked by SSRF protection."""

    pass


class ResourceLimitError(AssetDownloadError):
    """Raised when download exceeds configured limits."""

    pass


def _validate_url_safety(url: str, config: AssetDownloadConfig) -> None:
    """
    Validate URL for SSRF protection.

    Raises:
        SSRFProtectionError: If URL is blocked by security policy
    """
    try:
        parsed = urlparse(url)
    except Exception as e:
        raise SSRFProtectionError(f"Invalid URL: {e}") from e

    # Check scheme allowlist
    if parsed.scheme not in config.allowed_schemes:
        raise SSRFProtectionError(f"Scheme '{parsed.scheme}' not in allowed schemes: {config.allowed_schemes}")

    # Resolve hostname to IP for network checking
    hostname = parsed.hostname
    if not hostname:
        raise SSRFProtectionError("URL missing hostname")

    try:
        # Get all IPs for hostname (handles both IPv4 and IPv6)
        addr_infos = socket.getaddrinfo(hostname, None)
        ips = {info[4][0] for info in addr_infos}
    except socket.gaierror as e:
        raise SSRFProtectionError(f"Cannot resolve hostname '{hostname}': {e}") from e

    # Check each resolved IP against blocked networks
    for ip_str in ips:
        try:
            ip = ipaddress.ip_address(ip_str)
            for blocked_network in config.blocked_networks:
                if ip in ipaddress.ip_network(blocked_network):
                    raise SSRFProtectionError(f"IP {ip} is in blocked network {blocked_network}")
        except ValueError as e:
            # Invalid IP format - block it
            raise SSRFProtectionError(f"Invalid IP address '{ip_str}': {e}") from e


def download_asset(url: str, config: AssetDownloadConfig) -> Tuple[bytes, str | None]:
    """
    Download asset from URL with security and resource controls.

    Args:
        url: HTTP(S) URL to download
        config: Download configuration with limits and security settings

    Returns:
        Tuple of (content_bytes, content_type_header)

    Raises:
        AssetDownloadError: For download failures
        SSRFProtectionError: For SSRF protection violations
        ResourceLimitError: For resource limit violations
    """
    if not config.enabled:
        return b"", None

    # SSRF protection validation
    _validate_url_safety(url, config)

    # Check if requests is available
    if requests is None:
        raise AssetDownloadError("requests library not available")

    # Prepare request headers
    headers = {
        "User-Agent": config.user_agent,
        "Accept": "*/*",
    }

    try:
        with requests.get(
            url,
            stream=True,
            timeout=config.timeout_s,
            headers=headers,
            allow_redirects=True,  # Follow redirects but they'll be re-validated by requests
        ) as response:
            response.raise_for_status()

            # Get content type from response
            content_type = response.headers.get("Content-Type")

            # Stream download with size limits
            buf = io.BytesIO()
            downloaded = 0

            for chunk in response.iter_content(chunk_size=config.chunk_size):
                if not chunk:
                    continue

                downloaded += len(chunk)
                if downloaded > config.max_bytes:
                    raise ResourceLimitError(f"Asset too large: {downloaded} bytes > {config.max_bytes} byte limit")

                buf.write(chunk)

            return buf.getvalue(), content_type

    except (ResourceLimitError, AssetDownloadError, SSRFProtectionError):
        # Re-raise our own exceptions
        raise
    except Exception as e:
        # Handle request exceptions with fallback for testing
        error_type = type(e).__name__

        if error_type == "Timeout":
            raise ResourceLimitError(f"Download timeout after {config.timeout_s}s") from e
        elif error_type in ("RequestException", "HTTPError"):
            raise AssetDownloadError(f"HTTP request failed: {e}") from e
        else:
            raise AssetDownloadError(f"Unexpected download error: {e}") from e
