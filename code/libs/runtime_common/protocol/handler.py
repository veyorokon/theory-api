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

    Args:
        payload: {
            "run_id": str,
            "mode": "mock" | "real",
            "inputs": {
                "key": <presigned_url> | <local_path> | <inline_value>
            },
            "outputs": {
                "key": <presigned_put_url> | <local_path>
            }
        }

    Returns:
        {
            "kind": "Response",
            "control": {
                "run_id": str,
                "status": "success" | "error",
                "cost_micro": int,
                "final": bool
            },
            "outputs": {
                "key": <value>
            },
            "error": {  // Only if status == "error"
                "code": str,
                "message": str
            }
        }
    """
    run_id = str(payload.get("run_id", "")).strip()

    if not run_id:
        return {
            "kind": "Response",
            "control": {"run_id": "", "status": "error", "cost_micro": 0, "final": True},
            "error": {"code": "ERR_INPUTS", "message": "missing run_id"},
        }

    if emit:
        emit({"kind": "Event", "content": {"phase": "started"}})
        emit({"kind": "Log", "content": {"msg": "Using generic handler stub - override protocol/handler.py"}})
        emit({"kind": "Event", "content": {"phase": "completed"}})

    return {
        "kind": "Response",
        "control": {"run_id": run_id, "status": "success", "cost_micro": 0, "final": True},
        "outputs": {},
    }
