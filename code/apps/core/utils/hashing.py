# apps/core/utils/hashing.py
from __future__ import annotations
from blake3 import blake3

def blake3_cid(data: bytes) -> str:
    """Return 'b3:<hex>' content id."""
    return "b3:" + blake3(data).hexdigest()
