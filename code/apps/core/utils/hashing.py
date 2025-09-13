# apps/core/utils/hashing.py
from __future__ import annotations
import json
from blake3 import blake3


def blake3_cid(data: bytes) -> str:
    """Return 'b3:<hex>' content id."""
    return "b3:" + blake3(data).hexdigest()


def canonical_json_dumps(obj) -> str:
    """JCS-like canonicalization: sorted keys, UTF-8, no spaces."""
    # NOTE: if strict RFC-8785 needed, swap to a dedicated lib and bump schema.
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def blake3_hex(s: str) -> str:
    return blake3(s.encode("utf-8")).hexdigest()


def inputs_hash(inputs_obj) -> dict:
    raw = canonical_json_dumps(inputs_obj)
    return {"hash_schema": "jcs-blake3-v1", "value": blake3_hex(raw)}


def compose_env_fingerprint(**kv) -> str:
    parts = [f"{k}={v}" for k, v in kv.items() if v not in (None, "", False)]
    return ";".join(sorted(parts))
