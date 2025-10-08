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
from typing import Any, Dict, Union
import httpx


def make_scalar_uri(scheme: str, world_or_run: str, run_id: str, key: str, data: Any) -> str:
    """
    Create scalar artifact URI with embedded data.

    Args:
        scheme: "world" or "local"
        world_or_run: world_id for world://, run_id for local://
        run_id: run_id (used for world:// path)
        key: output key name
        data: JSON-serializable data to embed

    Returns:
        URI like "world://w/r/key?data=..." or "local://r/key?data=..."
    """
    if scheme == "world":
        base = f"world://{world_or_run}/{run_id}/{key}"
    else:  # local
        base = f"local://{world_or_run}/{key}"

    encoded_data = urllib.parse.quote(json.dumps(data, ensure_ascii=False))
    return f"{base}?data={encoded_data}"


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


def hydrate_inputs(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fetch inputs from presigned URLs or local paths.

    Args:
        inputs: {
            "key": "https://s3.../presigned-get" | "/artifacts/..." | <inline>
        }

    Returns:
        Hydrated dict with actual values
    """
    from pathlib import Path

    result = {}

    for key, value in inputs.items():
        if isinstance(value, str) and value.startswith("https://"):
            # Fetch from presigned GET URL
            response = httpx.get(value, timeout=30)
            response.raise_for_status()
            result[key] = response.content
        elif isinstance(value, str) and value.startswith("/artifacts/"):
            # Read from local filesystem
            result[key] = Path(value).read_bytes()
        else:
            # Inline value
            result[key] = value

    return result


def write_outputs(outputs_schema: Dict[str, str], results: Dict[str, Any]) -> None:
    """
    Write outputs to presigned PUT URLs or local paths.

    Args:
        outputs_schema: {
            "key": "https://s3.../presigned-put" | "/artifacts/..."
        }
        results: Tool's output data
    """
    from pathlib import Path

    for key, url in outputs_schema.items():
        if key not in results:
            continue

        data = results[key]

        # Convert to bytes
        if isinstance(data, str):
            content = data.encode("utf-8")
        elif isinstance(data, (dict, list)):
            content = json.dumps(data).encode("utf-8")
        elif isinstance(data, bytes):
            content = data
        else:
            content = json.dumps(data).encode("utf-8")

        # Write to destination
        if url.startswith("https://"):
            # Upload to presigned PUT URL
            response = httpx.put(url, content=content)
            response.raise_for_status()
        elif url.startswith("/artifacts/"):
            # Write to local filesystem
            path = Path(url)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
