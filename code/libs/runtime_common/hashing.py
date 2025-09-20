from __future__ import annotations
import json
from blake3 import blake3


def jcs_dumps(obj) -> str:
    """JSON Canonical Serialization-like dumps for deterministic hashing."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def blake3_hex(b: bytes) -> str:
    """BLAKE3 hash as hexadecimal string."""
    return blake3(b).hexdigest()


def blake3_cid(data: bytes) -> str:
    """Return 'b3:<hex>' content id."""
    return "b3:" + blake3(data).hexdigest()


def inputs_hash(payload: dict, *, schema: str = "jcs-blake3-v1") -> dict:
    """
    Compute deterministic hash of input payload.

    Args:
        payload: Input data to hash
        schema: Hash schema version for future upgrades

    Returns:
        Dict with hash_schema and value fields
    """
    s = jcs_dumps(payload)
    return {"hash_schema": schema, "value": blake3_hex(s.encode("utf-8"))}
