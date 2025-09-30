import os
import io
import json
from typing import Any, Dict, Callable, Optional
from .uploader import put_object, ensure_outputs_json


def entry(payload: Dict[str, Any], emit: Callable[[Dict], None] | None = None) -> Dict[str, Any]:
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
    if "{execution_id}" in write_prefix:
        write_prefix = write_prefix.replace("{execution_id}", execution_id)

    image_digest = os.getenv("IMAGE_DIGEST")
    if not image_digest:
        return {
            "status": "error",
            "execution_id": execution_id,
            "error": {"code": "ERR_IMAGE_DIGEST_MISSING", "message": "IMAGE_DIGEST not set"},
            "meta": {},
        }

    payload_json = json.dumps({"mode": mode, "inputs": inputs}, ensure_ascii=False)
    if emit:
        emit({"kind": "Event", "content": {"phase": "started"}})
        emit({"kind": "Log", "content": {"msg": "processing", "bytes": len(payload_json)}})

    etags = {}
    meta_key = "outputs/metadata.json"
    if meta_key not in put_urls:
        return {
            "status": "error",
            "execution_id": execution_id,
            "error": {"code": "ERR_UPLOAD_PLAN", "message": f"missing put_url for {meta_key}"},
            "meta": {},
        }
    try:
        etags[meta_key] = put_object(
            put_urls[meta_key], io.BytesIO(payload_json.encode("utf-8")), content_type="application/json"
        )
    except Exception as e:
        return {
            "status": "error",
            "execution_id": execution_id,
            "error": {"code": "ERR_UPLOAD", "message": f"Failed to upload {meta_key}: {str(e)}"},
            "meta": {},
        }

    index_key = "outputs.json"
    outputs_list = [{"path": f"{write_prefix}{meta_key}"}]
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

    meta = {"env_fingerprint": "cpu:1;memory:2Gi", "image_digest": image_digest, "proof": {"etag_map": etags}}
    if emit:
        emit({"kind": "Event", "content": {"phase": "completed"}})
    return {
        "status": "success",
        "execution_id": execution_id,
        "outputs": outputs_list,
        "index_path": f"{write_prefix}{index_key}",
        "meta": meta,
    }
