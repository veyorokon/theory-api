"""
Scope resolution service for converting agent intent to container-ready Request messages.

Django resolves .world/.local suffixes to presigned URLs before sending to container.
"""

from typing import Dict, Any
from django.conf import settings
from backend.storage.service import storage_service


def resolve_request(request_intent: Dict[str, Any], run) -> Dict[str, Any]:
    """
    Convert agent's request intent to container-ready Request message.

    Args:
        request_intent: {
            "mode": "mock" | "real",
            "inputs": {
                "key.world": "/path/in/world",
                "key.local": "/path/in/run",
                "key": <inline_value>
            },
            "outputs": {
                "key.world": "/path/in/world",
                "key.local": "/path/in/run"
            }
        }
        run: Run model instance

    Returns:
        {
            "kind": "Request",
            "control": {"run_id": str, "mode": str},
            "inputs": {
                "key": <presigned_get_url> | <local_path> | <inline>
            },
            "outputs": {
                "key": <presigned_put_url> | <local_path>
            }
        }
    """
    resolved_inputs = {}
    resolved_outputs = {}

    # Resolve inputs (where to READ from)
    for key, value in request_intent.get("inputs", {}).items():
        if key.endswith(".world"):
            base_key = key[:-6]
            s3_key = f"{run.world.id}/{value.lstrip('/')}"
            url = storage_service.get_download_url(key=s3_key, bucket=settings.STORAGE.get("BUCKET"), expires_in=3600)
            resolved_inputs[base_key] = url

        elif key.endswith(".local"):
            base_key = key[:-6]
            path = f"/artifacts/{run.id}/{value.lstrip('/')}"
            resolved_inputs[base_key] = path

        else:
            resolved_inputs[key] = value

    # Resolve outputs (where to WRITE to)
    for key, value in request_intent.get("outputs", {}).items():
        if key.endswith(".world"):
            base_key = key[:-6]
            s3_key = f"{run.world.id}/{value.lstrip('/')}"
            url = storage_service.get_upload_url(
                key=s3_key,
                bucket=settings.STORAGE.get("BUCKET"),
                expires_in=3600,
                content_type="application/octet-stream",
            )
            resolved_outputs[base_key] = url

        elif key.endswith(".local"):
            base_key = key[:-6]
            path = f"/artifacts/{run.id}/{value.lstrip('/')}"
            resolved_outputs[base_key] = path

    # Build container-ready Request
    return {
        "kind": "Request",
        "control": {"run_id": str(run.id), "mode": request_intent.get("mode", run.mode)},
        "inputs": resolved_inputs,
        "outputs": {k: v for k, v in resolved_outputs.items() if v is not None},
    }
