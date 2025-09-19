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
    execution_id: str, write_prefix: str, receipt: Dict[str, Any], global_base: str | None = None
) -> Dict[str, Any]:
    """
    Write identical receipts to both global and local locations.

    Args:
        execution_id: Unique execution identifier
        write_prefix: Local write prefix (with trailing /)
        receipt: Receipt dictionary to write
        global_base: Base path for global receipts (defaults to env vars or tmp)

    Returns:
        Dictionary with paths and success status for both writes
    """
    # Resolve base for global receipts
    base = global_base or os.getenv("ARTIFACTS_BASE_DIR") or os.path.join(os.getenv("TMPDIR", "/tmp"), "artifacts")

    global_path = f"{base.rstrip('/')}/execution/{execution_id}/determinism.json"
    local_path = f"{write_prefix.rstrip('/')}/receipt.json"

    # Write both; never crash the run if global write fails
    statuses = {"global_path": global_path, "local_path": local_path, "global_ok": False, "local_ok": False}

    # JSON bytes (identical for both locations)
    receipt_bytes = json.dumps(receipt, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

    # Write global receipt with error handling
    try:
        Path(os.path.dirname(global_path)).mkdir(parents=True, exist_ok=True)
        Path(global_path).write_bytes(receipt_bytes)
        statuses["global_ok"] = True
    except Exception as e:
        statuses["global_error"] = f"{type(e).__name__}: {e}"

    # Write local receipt with error handling
    try:
        Path(os.path.dirname(local_path)).mkdir(parents=True, exist_ok=True)
        Path(local_path).write_bytes(receipt_bytes)
        statuses["local_ok"] = True
    except Exception as e:
        statuses["local_error"] = f"{type(e).__name__}: {e}"

    return statuses


def build_processor_receipt(
    *,
    execution_id: str,
    processor_ref: str,
    schema: str,
    provider: str,
    model: str,
    model_version: str | None,
    inputs_hash: Dict[str, str],
    memo_key: str,
    env_fingerprint: str,
    image_digest: str,
    timestamp_utc: str,
    duration_ms: int,
    outputs_index_path: str,
    output_cids: list[str],
    stderr_tail: str,
    logs_excerpt: str,
    warnings: list[str],
) -> Dict[str, Any]:
    """
    Build standardized processor receipt for new processors.

    Args:
        execution_id: Unique execution identifier
        processor_ref: Processor reference (e.g., "replicate/generic@1")
        schema: Input schema version
        provider: Provider name (e.g., "replicate", "litellm")
        model: Model name
        model_version: Model version string
        inputs_hash: Hash of canonicalized inputs
        memo_key: Idempotency/memo key
        env_fingerprint: Environment fingerprint
        image_digest: Container image digest
        timestamp_utc: ISO timestamp
        duration_ms: Execution duration
        outputs_index_path: Path to outputs.json
        output_cids: List of output content IDs
        stderr_tail: Error output tail
        logs_excerpt: Execution logs excerpt
        warnings: List of warning messages

    Returns:
        Complete receipt dictionary
    """
    return {
        "execution_id": execution_id,
        "processor_ref": processor_ref,
        "schema": schema,
        "provider": provider,
        "model": model,
        "model_version": model_version,
        "inputs_hash": inputs_hash,
        "memo_key": memo_key,
        "env_fingerprint": env_fingerprint,
        "image_digest": image_digest,
        "timestamp_utc": timestamp_utc,
        "duration_ms": duration_ms,
        "outputs_index_path": outputs_index_path,
        "output_cids": output_cids,
        "stderr_tail": stderr_tail,
        "logs_excerpt": logs_excerpt,
        "warnings": warnings,
    }
