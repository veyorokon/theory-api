"""
Shared envelope helpers and minimal mode utilities.

Includes:
- success/error envelope builders
- envelope validator
- minimal mode resolution with CI safety
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Mapping


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
    execution_id: str,
    code: str,
    message: str,
    env_fingerprint: str,
    image_digest: str | None = None,
    duration_ms: int | None = None,
    stderr_tail: str | None = None,  # redacted short tail (<= 8KiB upstream)
    stderr_sha256: str | None = None,  # hash of full stderr (computed upstream)
    meta_extra: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Create standardized error envelope with nested error."""
    meta = {"env_fingerprint": env_fingerprint}
    if image_digest:
        meta["image_digest"] = image_digest
    if duration_ms is not None:
        meta["duration_ms"] = duration_ms
    if stderr_tail:
        meta["stderr_tail"] = stderr_tail
    if stderr_sha256:
        meta["stderr_sha256"] = stderr_sha256
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


def is_valid_envelope(obj: Any) -> tuple[bool, str]:
    """Validate envelope structure (adapter transport layer)."""
    if not isinstance(obj, dict):
        return False, "not_dict"

    status = obj.get("status")
    if status not in ("success", "error"):
        return False, f"invalid_status_{status}"

    if not obj.get("execution_id"):
        return False, "missing_execution_id"

    if status == "success":
        if not isinstance(obj.get("outputs"), list):
            return False, "outputs_not_list"
        if not isinstance(obj.get("index_path"), str):
            return False, "index_path_not_string"
    else:  # status == "error"
        error = obj.get("error")
        if not isinstance(error, dict):
            return False, "error_not_dict"
        if "code" not in error or "message" not in error:
            return False, "error_missing_fields"

    return True, ""


# Backwards-compatible alias for callers expecting 'validate_envelope'
validate_envelope = is_valid_envelope


# ---- Minimal mode utilities (merged from mode.py) ----

Mode = Literal["mock", "real"]


class ModeSafetyError(Exception):
    """Raised when the selected mode violates environment safety rules."""

    code = "ERR_CI_SAFETY"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class ResolvedMode:
    value: Mode


def resolve_mode(flag_value: str | Mapping[str, Any] | None) -> ResolvedMode:
    """
    Resolve "mock"|"real" with CI safety.

    Accepts a string or mapping containing a "mode" key; defaults to "mock".
    Blocks real mode when CI is set or when LANE/TEST_LANE == "pr".
    """
    raw = flag_value
    if isinstance(flag_value, Mapping):
        raw = flag_value.get("mode")

    v = (str(raw) if raw is not None else "mock").lower()
    if v not in ("mock", "real"):
        raise ValueError("Invalid mode '%s'. Allowed: ['mock', 'real']" % v)

    # CI safety: block real mode in CI or PR lane
    ci = os.getenv("CI", "")
    lane_env = os.getenv("LANE") or os.getenv("TEST_LANE")
    lane = lane_env.lower() if lane_env else None
    if v == "real" and (ci or lane == "pr"):
        raise ModeSafetyError("ERR_CI_SAFETY: Real mode is blocked in CI environments. Use mode=mock.")

    return ResolvedMode(value=v)  # type: ignore[arg-type]


def is_mock(resolved: ResolvedMode) -> bool:
    return resolved.value == "mock"


def is_real(resolved: ResolvedMode) -> bool:
    return resolved.value == "real"


# ---- Minimal types (moved from types.py) ----


@dataclass
class OutputItem:
    """Single output artifact from processor execution."""

    relpath: str
    bytes_: bytes
    mime: str = "application/octet-stream"
    meta: Mapping[str, str] | None = None


@dataclass
class ProcessorResult:
    """Standard result for all processors."""

    outputs: List[OutputItem] = field(default_factory=list)
    processor_info: str = ""
    usage: Mapping[str, Any] = field(default_factory=dict)
    extra: Mapping[str, Any] = field(default_factory=dict)
