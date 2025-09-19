import json
import mimetypes
import os
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List


def canonicalize_inputs(obj: Dict[str, Any]) -> Dict[str, Any]:
    """Canonicalize processor inputs for consistent hashing."""
    # Sort keys recursively for deterministic ordering
    if isinstance(obj, dict):
        return {k: canonicalize_inputs(v) for k, v in sorted(obj.items())}
    elif isinstance(obj, list):
        return [canonicalize_inputs(item) for item in obj]
    else:
        return obj


def content_address_bytes(data: bytes) -> str:
    """Generate content hash for bytes using BLAKE3."""
    import hashlib

    return f"b3:{hashlib.blake2b(data, digest_size=32).hexdigest()}"


def write_blob(prefix: str, relpath: str, data: bytes) -> Dict[str, Any]:
    """
    Write blob to content-addressed location and return metadata.

    Args:
        prefix: Write prefix (e.g., "/artifacts/outputs/")
        relpath: Relative path for the blob (e.g., "image/0.png")
        data: Raw bytes to write

    Returns:
        Dict with path, cid, size_bytes, mime fields
    """
    # Ensure prefix ends with /
    if not prefix.endswith("/"):
        prefix += "/"

    # Build full path
    full_path = prefix + relpath

    # Ensure directory exists
    os.makedirs(os.path.dirname(full_path), exist_ok=True)

    # Write data
    with open(full_path, "wb") as f:
        f.write(data)

    # Generate metadata
    cid = content_address_bytes(data)
    size_bytes = len(data)

    # Detect MIME type
    mime_type, _ = mimetypes.guess_type(relpath)
    if not mime_type:
        mime_type = "application/octet-stream"

    return {"path": full_path, "cid": cid, "size_bytes": size_bytes, "mime": mime_type}


def write_outputs(write_prefix: str, output_items) -> List[Path]:
    """
    Write output items to disk and return absolute paths.

    Args:
        write_prefix: Base directory for outputs (e.g., "/artifacts/exec123/")
        output_items: List of OutputItem objects

    Returns:
        List of absolute Path objects where files were written

    Raises:
        ValueError: If any relpath doesn't start with "outputs/"
    """
    from apps.core.integrations.types import OutputItem

    abs_paths = []
    for item in output_items:
        if not isinstance(item, OutputItem):
            raise TypeError(f"Expected OutputItem, got {type(item)}")

        # Enforce outputs/ prefix per Twin's requirement
        if not item.relpath.startswith("outputs/"):
            raise ValueError(f"OutputItem relpath must start with 'outputs/', got: {item.relpath}")

        # Ensure write_prefix ends with /
        prefix = write_prefix if write_prefix.endswith("/") else write_prefix + "/"
        full_path = Path(prefix) / item.relpath

        # Create parent directories
        full_path.parent.mkdir(parents=True, exist_ok=True)

        # Write bytes
        full_path.write_bytes(item.bytes_)
        abs_paths.append(full_path.resolve())

    return abs_paths


def write_outputs_index(execution_id: str, write_prefix: str, paths: List[Path]) -> Path:
    """
    Write standardized outputs index file.

    Args:
        execution_id: Execution identifier
        write_prefix: Base directory (e.g., "/artifacts/exec123/")
        paths: List of absolute Path objects for written outputs

    Returns:
        Path to the written outputs.json file

    Note:
        Creates object-wrapped, sorted index with path deduplication.
    """
    # Build output metadata
    outputs = []
    seen_paths = set()

    for path in sorted(paths, key=lambda p: str(p)):  # Sort for determinism
        path_str = str(path)
        if path_str in seen_paths:
            raise ValueError(f"Duplicate output path detected: {path_str}")
        seen_paths.add(path_str)

        # Read file for content addressing
        data = path.read_bytes()
        cid = content_address_bytes(data)

        # Detect MIME type
        mime_type, _ = mimetypes.guess_type(str(path))
        mime_type = mime_type or "application/octet-stream"

        outputs.append({"path": path_str, "cid": cid, "size_bytes": len(data), "mime": mime_type})

    # Write index
    prefix = write_prefix if write_prefix.endswith("/") else write_prefix + "/"
    index_path = Path(prefix) / "outputs.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {"outputs": outputs}
    index_path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    return index_path
