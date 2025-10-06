import os
import io
import json
from pathlib import Path
from typing import Any, Dict, Callable, Optional
from libs.runtime_common.protocol.uploader import put_object, ensure_outputs_json
from libs.runtime_common.hydration import resolve_inputs


# entry(payload, emit, ctrl) -> envelope
def entry(payload: Dict[str, Any], emit: Callable[[Dict], None] | None = None, ctrl=None) -> Dict[str, Any]:
    # Support both run_id and execution_id during transition
    run_id = str(payload.get("run_id") or payload.get("execution_id", "")).strip()
    mode = str(payload.get("mode", "mock")).strip()
    write_prefix = str(payload.get("write_prefix", "")).strip()

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

    # Expand run_id placeholder (support both single and double braces)
    write_prefix = write_prefix.replace("{{run_id}}", run_id).replace("{run_id}", run_id)
    # Default write_prefix if not provided
    if not write_prefix:
        write_prefix = f"{run_id}/"
    # Ensure trailing slash
    if not write_prefix.endswith("/"):
        write_prefix += "/"

    params = (inputs or {}).get("params") or {}
    messages = params.get("messages") or []
    model = params.get("model") or "gpt-4o-mini"

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
    reply_key = "text/response.txt"

    if outputs:
        # S3 artifact flow - upload to presigned URLs
        if reply_key not in outputs:
            return {
                "status": "error",
                "run_id": run_id,
                "error": {"code": "ERR_UPLOAD_PLAN", "message": f"missing put_url for {reply_key}"},
                "meta": {},
            }
        try:
            etags[reply_key] = put_object(outputs[reply_key], io.BytesIO(text.encode("utf-8")), content_type="text/plain")
        except Exception as e:
            return {
                "status": "error",
                "run_id": run_id,
                "error": {"code": "ERR_UPLOAD", "message": f"Failed to upload {reply_key}: {str(e)}"},
                "meta": {},
            }

        # outputs.json LAST
        index_key = "outputs.json"

        # Extract world_id from write_prefix (format: world_id/run_id/)
        parts = write_prefix.strip("/").split("/")
        world_id = parts[0] if len(parts) >= 2 else "unknown"

        outputs_list = [{"path": f"world://{world_id}/{run_id}/text/response.txt"}]
        index_bytes = ensure_outputs_json(outputs_list)

        if index_key not in outputs:
            return {
                "status": "error",
                "run_id": run_id,
                "error": {"code": "ERR_UPLOAD_PLAN", "message": f"missing put_url for {index_key}"},
                "meta": {},
            }
        try:
            etags[index_key] = put_object(outputs[index_key], io.BytesIO(index_bytes), content_type="application/json")
        except Exception as e:
            return {
                "status": "error",
                "run_id": run_id,
                "error": {"code": "ERR_UPLOAD", "message": f"Failed to upload {index_key}: {str(e)}"},
                "meta": {},
            }

        outputs_list = [{"path": f"world://{world_id}/{run_id}/text/response.txt"}]
        index_path = f"world://{world_id}/{run_id}/{index_key}"
    else:
        # Local container flow - write to /artifacts/{run_id}/
        local_path = Path(f"/artifacts/{run_id}/text/response.txt")
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(text.encode("utf-8"))

        # outputs.json LAST
        index_key = "outputs.json"
        outputs_list = [{"path": f"local://{run_id}/text/response.txt"}]
        index_bytes = ensure_outputs_json(outputs_list)

        index_local_path = Path(f"/artifacts/{run_id}/{index_key}")
        index_local_path.write_bytes(index_bytes)

        index_path = f"local://{run_id}/{index_key}"

    meta = {
        "env_fingerprint": "cpu:1;memory:2Gi",
        "image_digest": image_digest,
        "model": model,
        "proof": {"etag_map": etags} if outputs else {},
    }
    if emit:
        emit({"kind": "Event", "content": {"phase": "completed"}})
    return {
        "status": "success",
        "run_id": run_id,
        "outputs": outputs_list,
        "index_path": index_path,
        "meta": meta,
    }
