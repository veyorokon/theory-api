import os
import io
import json
from typing import Any, Dict, Callable, Optional
from .uploader import put_object, ensure_outputs_json


# entry(payload, emit, ctrl) -> envelope
def entry(payload: Dict[str, Any], emit: Callable[[Dict], None] | None = None, ctrl=None) -> Dict[str, Any]:
    execution_id = str(payload.get("execution_id", "")).strip()
    mode = str(payload.get("mode", "mock")).strip()
    write_prefix = str(payload.get("write_prefix", "")).strip()
    inputs = payload.get("inputs") or {}
    put_urls: Dict[str, str] = payload.get("put_urls") or {}

    if not execution_id:
        return {
            "status": "error",
            "execution_id": "",
            "error": {"code": "ERR_INPUTS", "message": "missing execution_id"},
            "meta": {},
        }
    # Expand execution_id placeholder (support both single and double braces)
    write_prefix = write_prefix.replace("{{execution_id}}", execution_id).replace("{execution_id}", execution_id)
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
                "execution_id": execution_id,
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
                "execution_id": execution_id,
                "error": {"code": "ERR_PROVIDER", "message": str(e)},
                "meta": {},
            }

    image_digest = os.getenv("IMAGE_DIGEST")
    if not image_digest:
        return {
            "status": "error",
            "execution_id": execution_id,
            "error": {"code": "ERR_IMAGE_DIGEST_MISSING", "message": "IMAGE_DIGEST not set"},
            "meta": {},
        }

    etags = {}
    reply_key = "outputs/text/response.txt"
    if reply_key not in put_urls:
        return {
            "status": "error",
            "execution_id": execution_id,
            "error": {"code": "ERR_UPLOAD_PLAN", "message": f"missing put_url for {reply_key}"},
            "meta": {},
        }
    try:
        etags[reply_key] = put_object(put_urls[reply_key], io.BytesIO(text.encode("utf-8")), content_type="text/plain")
    except Exception as e:
        return {
            "status": "error",
            "execution_id": execution_id,
            "error": {"code": "ERR_UPLOAD", "message": f"Failed to upload {reply_key}: {str(e)}"},
            "meta": {},
        }

    # outputs.json LAST
    index_key = "outputs.json"
    outputs_list = [{"path": f"{write_prefix}outputs/text/response.txt"}]
    index_bytes = ensure_outputs_json(outputs_list)
    if index_key not in put_urls:
        return {
            "status": "error",
            "execution_id": execution_id,
            "error": {"code": "ERR_UPLOAD_PLAN", "message": f"missing put_url for {index_key}"},
            "meta": {},
        }
    try:
        etags[index_key] = put_object(put_urls[index_key], io.BytesIO(index_bytes), content_type="application/json")
    except Exception as e:
        return {
            "status": "error",
            "execution_id": execution_id,
            "error": {"code": "ERR_UPLOAD", "message": f"Failed to upload {index_key}: {str(e)}"},
            "meta": {},
        }

    meta = {
        "env_fingerprint": "cpu:1;memory:2Gi",
        "image_digest": image_digest,
        "model": model,
        "proof": {"etag_map": etags},
    }
    if emit:
        emit({"kind": "Event", "content": {"phase": "completed"}})
    return {
        "status": "success",
        "execution_id": execution_id,
        "outputs": outputs_list,
        "index_path": f"{write_prefix}{index_key}",
        "meta": meta,
    }
