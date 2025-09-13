"""Determinism receipt generation utilities."""

from __future__ import annotations
import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, UTC
from pathlib import Path
from typing import Dict, Any


@dataclass
class Receipt:
    processor: str  # e.g., "llm/litellm@1"
    model: str | None  # "gpt-4o-mini" or None
    status: str  # "completed" | "failed"
    success: bool  # True for completed, False for failed
    execution_id: str  # UUID for this run
    inputs_fingerprint: str  # stable int/hash as string
    env_fingerprint: str  # adapter/image/memory/timeout/gpu/snapshot/region...
    image_digest: str | None  # "sha256:..." if known
    duration_ms: int
    timestamp_utc: str  # ISO 8601 Z
    extra: Dict[str, Any]  # any adapter-specific extras


def _iso_utc(dt: datetime) -> str:
    """Convert datetime to ISO UTC string with Z suffix."""
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def build_receipt(
    *,
    processor: str,
    model: str | None,
    status: str,  # "completed" | "failed"
    execution_id: str,
    inputs_fingerprint: str,
    env_fingerprint: str,
    image_ref: str | None,  # raw oci ref (for fallback)
    image_digest: str | None,
    started_at: datetime,
    finished_at: datetime | None = None,
    extra: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build complete receipt with all required fields for every processor run."""
    end = finished_at or datetime.now(UTC)
    duration_ms = int((end - started_at).total_seconds() * 1000)

    # Fallback: parse digest from OCI ref "…@sha256:…"
    if not image_digest and image_ref and "@sha256:" in image_ref:
        image_digest = image_ref.split("@", 1)[1]

    rec = Receipt(
        processor=processor,
        model=model,
        status=status,
        success=(status == "completed"),
        execution_id=execution_id,
        inputs_fingerprint=str(inputs_fingerprint),
        env_fingerprint=env_fingerprint or "",
        image_digest=image_digest,
        duration_ms=duration_ms,
        timestamp_utc=_iso_utc(end),
        extra=extra or {},
    )
    return asdict(rec)


def write_dual_receipts(
    execution_id: str, write_prefix: str, receipt: Dict[str, Any], global_base: str = "/artifacts"
) -> Dict[str, str]:
    """
    Write identical receipts to both global and local locations.

    Args:
        execution_id: Unique execution identifier
        write_prefix: Local write prefix (with trailing /)
        receipt: Receipt dictionary to write
        global_base: Base path for global receipts (for testing)

    Returns:
        Dictionary with global_path and local_path of written receipts
    """
    global_path = f"{global_base}/execution/{execution_id}/determinism.json"
    local_path = f"{write_prefix.rstrip('/')}/receipt.json"

    # JSON bytes (identical for both locations)
    receipt_bytes = json.dumps(receipt, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

    # Write to both locations
    for path in (global_path, local_path):
        Path(os.path.dirname(path)).mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(receipt_bytes)

    return {"global_path": global_path, "local_path": local_path}
