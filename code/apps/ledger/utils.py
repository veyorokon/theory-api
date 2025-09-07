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


def event_hash(payload: dict, include_ts: bool = False) -> str:
    """
    Compute hash of event payload using canonical JSON serialization.
    
    Args:
        payload: Event payload dictionary
        include_ts: Whether to include timestamp in hash computation
        
    Returns:
        Hex string hash of canonical payload
    """
    # Create copy to avoid mutating input
    obj = dict(payload)
    
    # Remove timestamp if not included in hash
    if not include_ts:
        obj.pop('ts', None)
        obj.pop('timestamp', None)
        obj.pop('created_at', None)
    
    # Generate canonical JSON (JCS-style: sorted keys, compact)
    canonical = json.dumps(obj, sort_keys=True, separators=(',', ':')).encode('utf-8')
    
    # Compute hash
    if BLAKE3_AVAILABLE:
        return blake3.blake3(canonical).hexdigest()
    else:
        # Fallback to SHA256 for development
        return hashlib.sha256(canonical).hexdigest()