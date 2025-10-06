"""
Generic handler stub - override this in your tool's protocol/handler.py.

Contract:
  entry(payload: dict, emit: callable | None, ctrl: Event | None) -> envelope: dict

Where:
  - payload: {"run_id": str, "mode": str, "inputs": dict, "outputs": dict | None, "write_prefix": str}
  - emit: callable to send events ({"kind": "Token"|"Event"|"Log", "content": {...}})
  - ctrl: multiprocessing.Event for cancellation (check ctrl.is_set())
  - outputs: If present, dict of {key: presigned_put_url}. If absent, write to /artifacts/{run_id}/

Returns envelope:
  {
    "status": "success"|"error",
    "run_id": str,
    "outputs": [{"path": "world://{world}/{run}/..." | "local://{run}/..."}, ...],
    "index_path": str,  # Optional
    "meta": {...},
    "error": {"code": str, "message": str}  # If status == error
  }
"""

from typing import Any, Dict, Callable, Optional


def entry(payload: Dict[str, Any], emit: Optional[Callable[[Dict], None]] = None, ctrl=None) -> Dict[str, Any]:
    """
    Generic mock handler - replace with tool-specific logic.

    To customize: create tools/{ns}/{name}/{ver}/protocol/handler.py with this signature.
    """
    # Support both run_id and execution_id during transition
    run_id = str(payload.get("run_id") or payload.get("execution_id", "")).strip()

    if not run_id:
        return {
            "status": "error",
            "run_id": "",
            "error": {"code": "ERR_INPUTS", "message": "missing run_id"},
            "meta": {},
        }

    if emit:
        emit({"kind": "Event", "content": {"phase": "started"}})
        emit({"kind": "Log", "content": {"msg": "Using generic handler stub - override protocol/handler.py"}})
        emit({"kind": "Event", "content": {"phase": "completed"}})

    return {
        "status": "success",
        "run_id": run_id,
        "outputs": [],
        "meta": {"note": "Override protocol/handler.py with tool-specific logic"},
    }
