"""
Shared envelope serializers for adapter canonical outputs.
"""

import json
from typing import Any, Dict, List


def success_envelope(
    execution_id: str,
    outputs: List[Dict[str, Any]],
    index_path: str,
    image_digest: str,
    env_fingerprint: str,
    duration_ms: int,
    meta_extra: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Create standardized success envelope."""
    meta = {"image_digest": image_digest, "env_fingerprint": env_fingerprint, "duration_ms": duration_ms}
    if meta_extra:
        meta.update(meta_extra)

    return {
        "status": "success",
        "execution_id": execution_id,
        "outputs": outputs,
        "index_path": index_path,
        "meta": meta,
    }


def error_envelope(
    execution_id: str, code: str, message: str, env_fingerprint: str, meta_extra: Dict[str, Any] | None = None
) -> Dict[str, Any]:
    """Create standardized error envelope with nested error."""
    meta = {"env_fingerprint": env_fingerprint}
    if meta_extra:
        meta.update(meta_extra)

    return {"status": "error", "execution_id": execution_id, "error": {"code": code, "message": message}, "meta": meta}


def write_outputs_index(index_path: str, entries: List[Dict[str, Any]]) -> bytes:
    """
    Write {"outputs":[...]} with sorted entries.
    Returns the JSON bytes for storage via artifact_store.
    """
    # Sort by path for deterministic output
    sorted_entries = sorted(entries, key=lambda e: e["path"])
    idx = {"outputs": sorted_entries}
    return json.dumps(idx, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
