"""
Generic handler stub - override this in your tool's protocol/handler.py.

Contract:
  entry(payload: dict, emit: callable | None, ctrl: Event | None) -> envelope: dict

Where:
  - payload: {"run_id": str, "mode": str, "inputs": dict, "outputs": dict | None}
  - emit: callable to send events ({"kind": "Token"|"Event"|"Log", "content": {...}})
  - ctrl: multiprocessing.Event for cancellation (check ctrl.is_set())
  - outputs: If present, dict of {key: presigned_put_url}. If absent, write to /artifacts/{run_id}/

Returns envelope:
  {
    "status": "success"|"error",
    "run_id": str,
    "outputs": {key: "world://{world}/{run}/key" | "local://{run}/key", ...},
    "meta": {...},
    "error": {"code": str, "message": str}  # If status == error
  }
"""

import yaml
from pathlib import Path
from typing import Any, Dict, Callable, Optional


def _load_env_fingerprint() -> str:
    """Load runtime spec from registry.yaml and construct env_fingerprint."""
    try:
        registry_path = Path(__file__).parent.parent / "registry.yaml"
        with open(registry_path) as f:
            reg = yaml.safe_load(f)
        runtime = reg.get("runtime") or {}
        cpu = runtime.get("cpu", "1")
        memory_gb = runtime.get("memory_gb", 2)
        gpu = runtime.get("gpu")

        parts = [f"cpu:{cpu}", f"memory:{memory_gb}Gi"]
        if gpu:
            parts.append(f"gpu:{gpu}")
        return ";".join(parts)
    except Exception:
        # Fallback if registry not readable
        return "cpu:1;memory:2Gi"


def entry(payload: Dict[str, Any], emit: Callable[[Dict], None] | None = None, ctrl=None) -> Dict[str, Any]:
    """
    Generic mock handler - replace with tool-specific logic.

    To customize: create tools/{ns}/{name}/{ver}/protocol/handler.py with this signature.
    """
    run_id = str(payload.get("run_id", "")).strip()
    env_fingerprint = _load_env_fingerprint()

    if not run_id:
        return {
            "status": "error",
            "run_id": "",
            "error": {"code": "ERR_INPUTS", "message": "missing run_id"},
            "meta": {"env_fingerprint": env_fingerprint},
        }

    if emit:
        emit({"kind": "Event", "content": {"phase": "started"}})
        emit({"kind": "Log", "content": {"msg": "Using generic handler stub - override protocol/handler.py"}})
        emit({"kind": "Event", "content": {"phase": "completed"}})

    return {
        "status": "success",
        "run_id": run_id,
        "outputs": {},
        "meta": {"env_fingerprint": env_fingerprint, "note": "Override protocol/handler.py with tool-specific logic"},
    }
