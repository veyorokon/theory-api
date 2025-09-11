"""
Shared envelope serializers for adapter canonical outputs.
"""
from typing import Any, Dict, List, Optional


def success_envelope(
    execution_id: str,
    outputs: List[Dict[str, Any]], 
    index_path: str,
    image_digest: str,
    env_fingerprint: str,
    duration_ms: int,
    meta_extra: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Create standardized success envelope."""
    meta = {
        'image_digest': image_digest,
        'env_fingerprint': env_fingerprint, 
        'duration_ms': duration_ms
    }
    if meta_extra:
        meta.update(meta_extra)
    
    return {
        'status': 'success',
        'execution_id': execution_id,
        'outputs': outputs,
        'index_path': index_path,
        'meta': meta
    }


def error_envelope(
    execution_id: str,
    code: str,
    message: str, 
    env_fingerprint: str,
    meta_extra: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Create standardized error envelope with nested error."""
    meta = {'env_fingerprint': env_fingerprint}
    if meta_extra:
        meta.update(meta_extra)
    
    return {
        'status': 'error',
        'execution_id': execution_id,
        'error': {'code': code, 'message': message},
        'meta': meta
    }