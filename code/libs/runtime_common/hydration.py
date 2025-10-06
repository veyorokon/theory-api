"""
Protocol layer utilities for resolving artifact URIs to actual data.

This module provides functions for containers to:
1. Resolve world:// URIs to actual data (fetch from URLs or extract from ?data=)
2. Convert artifact-based inputs to tool-specific formats
3. Write outputs to presigned PUT URLs
"""

from __future__ import annotations

import json
import urllib.parse
from typing import Any, Dict
import httpx


def resolve_artifact_uri(uri: str, timeout: int = 30) -> Any:
    """
    Resolve an artifact URI to actual data.

    Handles two cases:
    1. Scalar artifacts: world://...?data={json} → extract and decode JSON
    2. File artifacts: https://... (presigned URL) → fetch via HTTP GET

    Args:
        uri: Artifact URI (world:// with ?data= or https:// presigned URL)
        timeout: HTTP timeout in seconds

    Returns:
        Decoded data (dict/list for scalars, bytes for files)
    """
    if "?data=" in uri:
        # Scalar artifact - extract embedded JSON from query param
        query_start = uri.index("?data=")
        encoded_data = uri[query_start + 6 :]  # Skip "?data="
        json_str = urllib.parse.unquote(encoded_data)
        return json.loads(json_str)

    elif uri.startswith("http://") or uri.startswith("https://"):
        # File artifact - fetch from presigned URL
        response = httpx.get(uri, timeout=timeout, follow_redirects=True)
        response.raise_for_status()

        # Try to decode as JSON first, fallback to bytes
        content_type = response.headers.get("content-type", "")
        if "json" in content_type:
            return response.json()
        else:
            return response.content

    else:
        raise ValueError(f"Unsupported URI format: {uri}")


def resolve_inputs(inputs: Dict[str, Any], timeout: int = 30) -> Dict[str, Any]:
    """
    Recursively resolve all artifact URIs in inputs dict.

    Args:
        inputs: Input dict with artifact URIs
        timeout: HTTP timeout in seconds

    Returns:
        Resolved inputs dict with actual data
    """
    resolved = {}

    for key, value in inputs.items():
        if isinstance(value, str) and ("?data=" in value or value.startswith("http")):
            # It's an artifact URI - resolve it
            resolved[key] = resolve_artifact_uri(value, timeout)
        elif isinstance(value, dict):
            # Nested dict - recurse
            resolved[key] = resolve_inputs(value, timeout)
        elif isinstance(value, list):
            # List - resolve each item
            resolved[key] = [
                resolve_artifact_uri(item, timeout)
                if isinstance(item, str) and ("?data=" in item or item.startswith("http"))
                else item
                for item in value
            ]
        else:
            # Primitive value - keep as-is
            resolved[key] = value

    return resolved


def write_output(url: str, data: bytes, content_type: str = "application/octet-stream", timeout: int = 30) -> None:
    """
    Write output data to presigned PUT URL.

    Args:
        url: Presigned PUT URL
        data: Output data as bytes
        content_type: MIME type
        timeout: HTTP timeout in seconds
    """
    response = httpx.put(url, content=data, headers={"Content-Type": content_type}, timeout=timeout)
    response.raise_for_status()


def write_outputs(output_urls: Dict[str, str], results: Dict[str, Any], timeout: int = 30) -> None:
    """
    Write multiple outputs to their presigned PUT URLs.

    Args:
        output_urls: Dict mapping keys to presigned PUT URLs
        results: Dict with output data (matching keys)
        timeout: HTTP timeout in seconds
    """
    for key, url in output_urls.items():
        if key not in results:
            continue

        data = results[key]

        # Convert to bytes if needed
        if isinstance(data, str):
            content = data.encode("utf-8")
            content_type = "text/plain"
        elif isinstance(data, (dict, list)):
            content = json.dumps(data).encode("utf-8")
            content_type = "application/json"
        elif isinstance(data, bytes):
            content = data
            content_type = "application/octet-stream"
        else:
            # Fallback: JSON encode
            content = json.dumps(data).encode("utf-8")
            content_type = "application/json"

        write_output(url, content, content_type, timeout)
