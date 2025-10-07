import os
import io
import json
import yaml
from pathlib import Path
from typing import Any, Dict, Callable, Optional
from libs.runtime_common.protocol.uploader import put_object
from libs.runtime_common.hydration import resolve_inputs, make_scalar_uri


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


# entry(payload, emit, ctrl) -> envelope
def entry(payload: Dict[str, Any], emit: Callable[[Dict], None] | None = None, ctrl=None) -> Dict[str, Any]:
    run_id = str(payload.get("run_id", "")).strip()
    mode = str(payload.get("mode", "mock")).strip()

    # Hydrate inputs: resolve world:// URIs to actual data
    raw_inputs = payload.get("inputs") or {}
    inputs = resolve_inputs(raw_inputs)

    # Check if outputs field present (determines S3 vs local)
    outputs = payload.get("outputs")

    if not run_id:
        return {
            "status": "error",
            "run_id": "",
            "error": {"code": "ERR_INPUTS", "message": "missing run_id"},
            "meta": {},
        }

    params = (inputs or {}).get("params") or {}
    messages = params.get("messages") or []
    model = params.get("model") or "gpt-4o-mini"
    strict = (inputs or {}).get("strict", False)

    env_fingerprint = _load_env_fingerprint()

    # Validate inputs if strict mode or real mode
    if strict or mode == "real":
        if not messages:
            return {
                "status": "error",
                "run_id": run_id,
                "error": {"code": "ERR_VALIDATION", "message": "messages cannot be empty"},
                "meta": {"env_fingerprint": env_fingerprint},
            }
        if not all(isinstance(m, dict) and "role" in m and "content" in m for m in messages):
            return {
                "status": "error",
                "run_id": run_id,
                "error": {"code": "ERR_VALIDATION", "message": "messages must be [{role, content}, ...]"},
                "meta": {"env_fingerprint": env_fingerprint},
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
                "status": "error",
                "run_id": run_id,
                "error": {"code": "ERR_MISSING_SECRET", "message": "OPENAI_API_KEY missing"},
                "meta": {},
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
                "status": "error",
                "run_id": run_id,
                "error": {"code": "ERR_PROVIDER", "message": str(e)},
                "meta": {},
            }

    image_digest = os.getenv("IMAGE_DIGEST")
    if not image_digest:
        return {
            "status": "error",
            "run_id": run_id,
            "error": {"code": "ERR_IMAGE_DIGEST_MISSING", "message": "IMAGE_DIGEST not set"},
            "meta": {},
        }

    etags = {}
    outputs_result = {}

    if outputs:
        # S3 artifact flow - upload to presigned URLs
        if "response" not in outputs:
            return {
                "status": "error",
                "run_id": run_id,
                "error": {"code": "ERR_UPLOAD_PLAN", "message": "missing put_url for response"},
                "meta": {},
            }
        try:
            etags["response"] = put_object(
                outputs["response"], io.BytesIO(text.encode("utf-8")), content_type="text/plain"
            )
            # Response is scalar - embed in URI
            outputs_result["response"] = make_scalar_uri("world", "unknown", run_id, "response", text)
        except Exception as e:
            return {
                "status": "error",
                "run_id": run_id,
                "error": {"code": "ERR_UPLOAD", "message": f"Failed to upload response: {str(e)}"},
                "meta": {},
            }

        # Usage output
        if "usage" in outputs:
            usage_data = {"prompt_tokens": 0, "completion_tokens": len(text.split())}
            try:
                etags["usage"] = put_object(
                    outputs["usage"],
                    io.BytesIO(json.dumps(usage_data).encode("utf-8")),
                    content_type="application/json",
                )
                outputs_result["usage"] = make_scalar_uri("world", "unknown", run_id, "usage", usage_data)
            except Exception as e:
                return {
                    "status": "error",
                    "run_id": run_id,
                    "error": {"code": "ERR_UPLOAD", "message": f"Failed to upload usage: {str(e)}"},
                    "meta": {},
                }
    else:
        # Local container flow - write to /artifacts/{run_id}/
        local_path = Path(f"/artifacts/{run_id}/response.txt")
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(text.encode("utf-8"))

        # Response is scalar - embed in URI
        outputs_result["response"] = make_scalar_uri("local", run_id, run_id, "response", text)

        # Usage output
        usage_data = {"prompt_tokens": 0, "completion_tokens": len(text.split())}
        usage_path = Path(f"/artifacts/{run_id}/usage.json")
        usage_path.write_bytes(json.dumps(usage_data).encode("utf-8"))
        outputs_result["usage"] = make_scalar_uri("local", run_id, run_id, "usage", usage_data)

    meta = {
        "env_fingerprint": env_fingerprint,
        "image_digest": image_digest,
        "model": model,
        "proof": {"etag_map": etags} if outputs else {},
    }
    if emit:
        emit({"kind": "Event", "content": {"phase": "completed"}})
    return {
        "status": "success",
        "run_id": run_id,
        "outputs": outputs_result,
        "meta": meta,
    }
