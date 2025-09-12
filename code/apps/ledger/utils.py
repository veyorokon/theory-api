"""
Utility functions for ledger hashing and canonicalization.
"""

import json

try:
    import blake3

    BLAKE3_AVAILABLE = True
except ImportError:
    import hashlib

    BLAKE3_AVAILABLE = False


def event_hash(payload: dict, prev_hash: str | None = None, include_ts: bool = True) -> str:
    """
    Compute hash of event payload using canonical JSON serialization with prev_hash chaining.

    Args:
        payload: Event payload dictionary
        prev_hash: Previous event hash to include in chain (hex string)
        include_ts: Whether to include timestamp in hash computation (default True)

    Returns:
        Hex string hash of prev_hash + canonical payload
    """
    # Create copy to avoid mutating input
    obj = dict(payload)

    # Remove timestamp if not included in hash (backwards compatibility)
    if not include_ts:
        obj.pop("ts", None)
        obj.pop("timestamp", None)
        obj.pop("created_at", None)

    # Generate canonical JSON (JCS-style: sorted keys, compact)
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")

    # Prepend previous hash bytes if provided
    prefix = bytes.fromhex(prev_hash) if prev_hash else b""

    # Compute hash
    if BLAKE3_AVAILABLE:
        return blake3.blake3(prefix + canonical).hexdigest()
    else:
        # Fallback to SHA256 for development
        return hashlib.sha256(prefix + canonical).hexdigest()
