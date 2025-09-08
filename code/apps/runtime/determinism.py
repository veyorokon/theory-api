"""
Determinism receipt helper (MVP).
Writes /artifacts/execution/<id>/determinism.json and returns the WorldPath.
"""
from __future__ import annotations
import json
from typing import List
from apps.plans.models import Plan
from apps.runtime.models import Execution
from apps.storage.service import storage_service

def write_determinism_receipt(
    plan: Plan,
    execution: Execution,
    *,
    seed: int,
    memo_key: str,
    env_fingerprint: str,
    output_cids: List[str],
) -> str:
    payload = {
        "seed": int(seed),
        "memo_key": str(memo_key),
        "env_fingerprint": str(env_fingerprint),
        "output_cids": list(output_cids or []),
    }
    data = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    path = f"/artifacts/execution/{execution.id}/determinism.json"
    storage_service.upload_bytes(
        data, key=path, content_type="application/json", bucket='default'
    )
    return path
