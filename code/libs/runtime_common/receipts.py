"""Determinism receipt generation utilities."""

from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, UTC
from typing import Dict, Any


@dataclass
class Receipt:
    processor: str               # e.g., "llm/litellm@1"
    model: str | None           # "gpt-4o-mini" or None
    status: str                 # "completed" | "failed"
    success: bool               # True for completed, False for failed
    execution_id: str           # UUID for this run
    inputs_fingerprint: str     # stable int/hash as string
    env_fingerprint: str        # adapter/image/memory/timeout/gpu/snapshot/region...
    image_digest: str | None    # "sha256:..." if known
    duration_ms: int
    timestamp_utc: str          # ISO 8601 Z
    extra: Dict[str, Any]       # any adapter-specific extras


def _iso_utc(dt: datetime) -> str:
    """Convert datetime to ISO UTC string with Z suffix."""
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def build_receipt(
    *,
    processor: str,
    model: str | None,
    status: str,                   # "completed" | "failed"
    execution_id: str,
    inputs_fingerprint: str,
    env_fingerprint: str,
    image_ref: str | None,         # raw oci ref (for fallback)
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