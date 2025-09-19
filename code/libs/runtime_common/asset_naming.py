# libs/runtime_common/asset_naming.py
"""
Deterministic asset naming and receipt generation.

Provides consistent, content-addressed naming for downloaded assets with:
- BLAKE3 content hashing for deterministic names
- Source URL receipts and metadata tracking
- Extension detection from content-type and URL
- Collision-resistant naming schemes
"""

from __future__ import annotations
import hashlib
import mimetypes
import re
from dataclasses import dataclass
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse

try:
    import blake3  # type: ignore

    HAS_BLAKE3 = True
except ImportError:
    import hashlib

    HAS_BLAKE3 = False


@dataclass
class AssetReceipt:
    """Receipt for a downloaded asset with deterministic naming."""

    # Content identification
    content_hash: str  # BLAKE3 or SHA256 hash of content
    content_size: int  # Size in bytes

    # Source tracking
    source_url: str  # Original URL
    download_timestamp: str  # ISO timestamp when downloaded

    # File information
    filename: str  # Deterministic filename
    content_type: str | None = None  # MIME type from HTTP headers
    extension: str = ".bin"  # File extension

    # Additional metadata
    metadata: Dict[str, str] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


def _compute_content_hash(content: bytes) -> str:
    """Compute deterministic hash of content using BLAKE3 or SHA256."""
    if HAS_BLAKE3:
        return blake3.blake3(content).hexdigest()
    else:
        return hashlib.sha256(content).hexdigest()


def _safe_extension_from_content_type(content_type: str | None) -> str:
    """Get file extension from content-type with safe fallbacks."""
    if not content_type:
        return ".bin"

    # Clean content type (remove charset, etc.)
    clean_type = content_type.split(";")[0].strip().lower()

    # Common mappings for reliable extensions
    type_mapping = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "image/svg+xml": ".svg",
        "application/json": ".json",
        "text/plain": ".txt",
        "text/html": ".html",
        "text/csv": ".csv",
        "video/mp4": ".mp4",
        "video/webm": ".webm",
        "audio/mpeg": ".mp3",
        "audio/wav": ".wav",
        "application/pdf": ".pdf",
    }

    if clean_type in type_mapping:
        return type_mapping[clean_type]

    # Try mimetypes library as fallback
    ext = mimetypes.guess_extension(clean_type)
    if ext:
        return ext

    # Generic fallbacks based on main type
    main_type = clean_type.split("/")[0]
    fallback_mapping = {
        "image": ".img",
        "video": ".vid",
        "audio": ".aud",
        "text": ".txt",
        "application": ".bin",
    }

    return fallback_mapping.get(main_type, ".bin")


def _extension_from_url(url: str) -> str | None:
    """Extract file extension from URL path."""
    try:
        parsed = urlparse(url)
        path = parsed.path
        if "." in path:
            ext = path.split(".")[-1].lower()
            # Validate extension (alphanumeric only, max 6 chars)
            if re.match(r"^[a-z0-9]{1,6}$", ext):
                return f".{ext}"
    except Exception:
        pass
    return None


def _sanitize_filename_part(name: str, max_length: int = 50) -> str:
    """Sanitize filename component for cross-platform compatibility."""
    # Remove/replace problematic characters
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)

    # Replace multiple underscores/spaces with single underscore
    sanitized = re.sub(r"[_\s]+", "_", sanitized)

    # Remove leading/trailing underscores and dots
    sanitized = sanitized.strip("_. ")

    # Truncate to max length
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length].rstrip("_. ")

    return sanitized or "asset"


def determine_asset_extension(content_type: str | None, source_url: str) -> str:
    """
    Determine best file extension for asset.

    Priority order:
    1. Content-type header
    2. URL file extension
    3. Generic fallback
    """
    # Try content-type first (most reliable)
    ext = _safe_extension_from_content_type(content_type)
    if ext != ".bin":
        return ext

    # Try URL extension as fallback
    url_ext = _extension_from_url(source_url)
    if url_ext:
        return url_ext

    # Final fallback
    return ".bin"


def generate_deterministic_filename(
    content: bytes, source_url: str, content_type: str | None = None, include_source_hint: bool = True
) -> Tuple[str, str]:
    """
    Generate deterministic filename for asset content.

    Returns:
        Tuple of (filename, content_hash)
    """
    # Compute content hash
    content_hash = _compute_content_hash(content)

    # Determine extension
    extension = determine_asset_extension(content_type, source_url)

    if include_source_hint:
        # Extract hint from URL
        try:
            parsed = urlparse(source_url)
            domain_hint = parsed.netloc.split(".")[-2] if "." in parsed.netloc else parsed.netloc
            domain_hint = _sanitize_filename_part(domain_hint, 20)

            # Use first 12 chars of hash + domain hint + extension
            filename = f"{content_hash[:12]}_{domain_hint}{extension}"
        except Exception:
            # Fallback to hash-only naming
            filename = f"{content_hash[:16]}{extension}"
    else:
        # Pure content-addressed naming
        filename = f"{content_hash[:16]}{extension}"

    return filename, content_hash


def create_asset_receipt(
    content: bytes,
    source_url: str,
    content_type: str | None = None,
    download_timestamp: str | None = None,
    additional_metadata: Dict[str, str] | None = None,
) -> AssetReceipt:
    """
    Create complete asset receipt with deterministic naming.

    Args:
        content: Raw asset content bytes
        source_url: Original download URL
        content_type: MIME type from HTTP headers
        download_timestamp: ISO timestamp (uses current time if None)
        additional_metadata: Extra metadata to include

    Returns:
        AssetReceipt with deterministic filename and content hash
    """
    import time

    # Generate deterministic filename and hash
    filename, content_hash = generate_deterministic_filename(
        content, source_url, content_type, include_source_hint=True
    )

    # Use current timestamp if not provided
    if download_timestamp is None:
        download_timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # Determine extension
    extension = determine_asset_extension(content_type, source_url)

    # Build metadata
    metadata = {
        "source_url": source_url,
        "download_timestamp": download_timestamp,
    }
    if content_type:
        metadata["content_type"] = content_type
    if additional_metadata:
        metadata.update(additional_metadata)

    return AssetReceipt(
        content_hash=content_hash,
        content_size=len(content),
        source_url=source_url,
        download_timestamp=download_timestamp,
        filename=filename,
        content_type=content_type,
        extension=extension,
        metadata=metadata,
    )
