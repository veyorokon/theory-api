import os
import io
import json
import yaml
from pathlib import Path
from typing import Any, Dict, Callable, Optional
from libs.runtime_common.hydration import hydrate_inputs, write_outputs


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


# entry(payload, emit, ctrl) -> Response
def entry(payload: Dict[str, Any], emit: Callable[[Dict], None] | None = None, ctrl=None) -> Dict[str, Any]:
    run_id = str(payload.get("run_id", "")).strip()
    mode = str(payload.get("mode", "mock")).strip()

    # Hydrate inputs: fetch from presigned URLs or local paths
    raw_inputs = payload.get("inputs") or {}
    inputs = hydrate_inputs(raw_inputs)

    # Get output schema (where to write)
    outputs_schema = payload.get("outputs", {})

    if not run_id:
        return {
            "kind": "Response",
            "control": {"run_id": "", "status": "error", "cost_micro": 0, "final": True},
            "error": {"code": "ERR_INPUTS", "message": "missing run_id"},
        }

    params = (inputs or {}).get("params") or {}
    messages = params.get("messages") or []
    model = params.get("model") or "gpt-4o-mini"
    strict = (inputs or {}).get("strict", False)

    # Validate inputs if strict mode or real mode
    if strict or mode == "real":
        if not messages:
            return {
                "kind": "Response",
                "control": {"run_id": run_id, "status": "error", "cost_micro": 0, "final": True},
                "error": {"code": "ERR_VALIDATION", "message": "messages cannot be empty"},
            }
        if not all(isinstance(m, dict) and "role" in m and "content" in m for m in messages):
            return {
                "kind": "Response",
                "control": {"run_id": run_id, "status": "error", "cost_micro": 0, "final": True},
                "error": {"code": "ERR_VALIDATION", "message": "messages must be [{role, content}, ...]"},
            }

    if emit:
        emit({"kind": "Event", "content": {"phase": "started"}})

    if mode == "mock":
        text = f"Mock response: {messages[-1]['content'][:64] if messages else ''}"
        if emit:
            for chunk in text.split():
                if ctrl and getattr(ctrl, "is_set", lambda: False)():
                    break
                emit({"kind": "Token", "content": {"text": chunk + " "}})
    else:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return {
                "kind": "Response",
                "control": {"run_id": run_id, "status": "error", "cost_micro": 0, "final": True},
                "error": {"code": "ERR_MISSING_SECRET", "message": "OPENAI_API_KEY missing"},
            }
        try:
            import litellm

            resp = litellm.completion(model=model, messages=messages, stream=True)
            parts = []
            for ev in resp:
                if ctrl and getattr(ctrl, "is_set", lambda: False)():
                    break
                delta = getattr(ev.choices[0].delta, "content", "") if hasattr(ev.choices[0], "delta") else ""
                if delta:
                    parts.append(delta)
                    if emit:
                        emit({"kind": "Token", "content": {"text": delta}})
            text = "".join(parts)
        except Exception as e:
            return {
                "kind": "Response",
                "control": {"run_id": run_id, "status": "error", "cost_micro": 0, "final": True},
                "error": {"code": "ERR_PROVIDER", "message": str(e)},
            }

    # Write outputs
    write_outputs(
        outputs_schema, {"response": text, "usage": {"prompt_tokens": 0, "completion_tokens": len(text.split())}}
    )

    # Placeholder cost - TODO: calculate API + compute costs
    cost_micro = 100

    if emit:
        emit({"kind": "Event", "content": {"phase": "completed"}})

    return {
        "kind": "Response",
        "control": {"run_id": run_id, "status": "success", "cost_micro": cost_micro, "final": True},
        "outputs": {
            "response": outputs_schema.get("response") if outputs_schema else None,
            "tokens": len(text.split()),  # Inline result
        },
    }
