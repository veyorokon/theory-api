import os
from typing import Any, Dict, List
from .receipts import write_outputs_and_receipts
from .logging import info


def entry(payload: Dict[str, Any]) -> Dict[str, Any]:
    # Basic shape checks (envelope-level)
    execution_id = str(payload.get("execution_id", "")).strip()
    mode = str(payload.get("mode", "mock")).strip()
    write_prefix = str(payload.get("write_prefix", "")).strip()
    inputs = payload.get("inputs") or {}

    if not execution_id:
        return {
            "status": "error",
            "execution_id": "",
            "error": {"code": "ERR_INPUTS", "message": "missing execution_id"},
            "meta": {},
        }
    if "{execution_id}" in write_prefix:
        write_prefix = write_prefix.replace("{execution_id}", execution_id)

    params = (inputs or {}).get("params") or {}
    messages: List[Dict[str, str]] = params.get("messages") or []
    model = params.get("model") or "gpt-4o-mini"

    # Mock path is hermetic (no secrets)
    if mode == "mock":
        text = f"Mock response: {messages[-1]['content'][:64] if messages else ''}"
    else:
        # Real path: secrets required
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return {
                "status": "error",
                "execution_id": execution_id,
                "error": {"code": "ERR_MISSING_SECRET", "message": "OPENAI_API_KEY missing"},
                "meta": {},
            }

        # Lazy import with defensive fallback
        try:
            import litellm

            resp = litellm.completion(model=model, messages=messages)
            text = resp.choices[0].message.get("content") if hasattr(resp, "choices") else str(resp)
        except ImportError:
            return {
                "status": "error",
                "execution_id": execution_id,
                "error": {"code": "ERR_RUNTIME", "message": "litellm not installed in image"},
                "meta": {},
            }
        except Exception as e:
            return {
                "status": "error",
                "execution_id": execution_id,
                "error": {"code": "ERR_PROVIDER", "message": f"{type(e).__name__}: {e}"},
                "meta": {},
            }

    # Strict digest validation
    image_digest = os.environ.get("IMAGE_DIGEST")
    if not image_digest:
        return {
            "status": "error",
            "execution_id": execution_id,
            "error": {"code": "ERR_IMAGE_DIGEST_MISSING", "message": "IMAGE_DIGEST env var not set"},
            "meta": {},
        }

    meta = {"env_fingerprint": "cpu:1;memory:2Gi", "model": model, "image_digest": image_digest}

    info("handler.llm.ok", execution_id=execution_id, write_prefix=write_prefix)
    return write_outputs_and_receipts(
        execution_id=execution_id, write_prefix=write_prefix, meta=meta, outputs=[("text/response.txt", text)]
    )
