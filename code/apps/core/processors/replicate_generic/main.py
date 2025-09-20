"""Replicate (generic) processor entrypoint (thin pattern, provider-agnostic).

Contract:
- No Django imports.
- Uses shared runtime_common helpers for I/O, hashing, outputs, receipts.
- Provider surface: make_runner(ProviderConfig) -> callable(inputs: dict) -> ProcessorResult
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any, Dict

from libs.runtime_common.processor import parse_args, load_inputs, ensure_write_prefix, ProviderConfig
from libs.runtime_common.hashing import inputs_hash
from libs.runtime_common.fingerprint import compose_env_fingerprint
from libs.runtime_common.outputs import write_outputs, write_outputs_index
from libs.runtime_common.receipts import write_dual_receipts

from .provider import make_runner  # module execution handles this correctly


# --- Input normalization (schema v1) -----------------------------------------


def _normalize_inputs_legacy_to_v1(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Accept replicate legacy shapes and normalize to:
    {
      "schema": "v1",
      "model": Optional[str],
      "params": {...},    # replicate input/params
      "files": {...},     # optional (urls or world:// refs)
      "mode": "default|mock|orchestrator"
    }
    """
    if payload.get("schema") == "v1":
        return payload

    # Replicate legacy could be {"model": "...", "input": {...}} or {"params": {...}}
    if "input" in payload and "params" not in payload:
        return {
            "schema": "v1",
            "model": payload.get("model"),
            "params": payload["input"],
            "files": payload.get("files", {}),
            "mode": payload.get("mode", "default"),
        }
    if "params" in payload:
        return {
            "schema": "v1",
            "model": payload.get("model"),
            "params": payload["params"],
            "files": payload.get("files", {}),
            "mode": payload.get("mode", "default"),
        }

    # Fallback minimal wrapper
    return {
        "schema": "v1",
        "model": payload.get("model"),
        "params": payload,
        "files": payload.get("files", {}),
        "mode": payload.get("mode", "default"),
    }


def _should_mock(mode: str) -> bool:
    if os.getenv("CI", "").lower() == "true":
        return True
    return mode.lower() == "mock"


def _env_fingerprint() -> str:
    return compose_env_fingerprint(
        image=os.getenv("IMAGE_REF", "unknown"),
        cpu=os.getenv("CPU", "1"),
        memory=os.getenv("MEMORY", "2Gi"),
        py=os.getenv("PYTHON_VERSION", ""),
        gpu=os.getenv("GPU", "none"),
    )


# --- Main --------------------------------------------------------------------


def main() -> int:
    args = parse_args()
    write_prefix = ensure_write_prefix(args.write_prefix)
    raw_inputs = load_inputs(args.inputs)
    inputs_v1 = _normalize_inputs_legacy_to_v1(raw_inputs)

    ih = inputs_hash(inputs_v1)

    mode = (inputs_v1.get("mode") or "default").lower()
    cfg = ProviderConfig(
        mock=_should_mock(mode),
        model=inputs_v1.get("model"),
        extra={},  # free-form metadata to the provider, if needed
    )

    runner = make_runner(cfg)

    t0 = time.time()
    result = runner(inputs_v1)
    duration_ms = int((time.time() - t0) * 1000)

    abs_paths = write_outputs(write_prefix, result.outputs, enforce_outputs_prefix=True)
    index_path = write_outputs_index(
        execution_id=args.execution_id,
        write_prefix=write_prefix,
        paths=abs_paths,
    )

    receipt = {
        "execution_id": args.execution_id,
        "processor_ref": os.getenv("PROCESSOR_REF", "replicate/generic@1"),
        "image_digest": os.getenv("IMAGE_REF", "unknown"),
        "env_fingerprint": _env_fingerprint(),
        "inputs_hash": ih["value"],
        "hash_schema": ih["hash_schema"],
        "outputs_index": str(index_path),
        "processor_info": result.processor_info,
        "usage": result.usage,
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "duration_ms": duration_ms,
        "extra": result.extra,
    }
    write_dual_receipts(args.execution_id, write_prefix, receipt)

    return 0


if __name__ == "__main__":
    sys.exit(main())
