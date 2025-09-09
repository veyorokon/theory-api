"""
Environment fingerprint utilities for determinism receipts.

Provides stable, JCS-hashed environment specifications for reproducibility.
"""
import json
from typing import Dict, List, Any

try:
    import blake3
    BLAKE3_AVAILABLE = True
except ImportError:
    import hashlib
    BLAKE3_AVAILABLE = False


def compose_env_fingerprint(
    image_digest: str,
    runtime: Dict[str, Any],
    versions: Dict[str, str],
    present_env_keys: List[str]
) -> str:
    """
    Compose environment fingerprint from execution context.
    
    Args:
        image_digest: Container image digest or identifier
        runtime: Runtime configuration (cpu, memory, gpu, etc.)
        versions: Version information (python, packages, etc.)
        present_env_keys: List of environment variable names that were present
                         (names only, not values for security)
    
    Returns:
        Stable JCS-hashed environment fingerprint string
    """
    # Compose fingerprint object
    fingerprint_obj = {
        'image_digest': str(image_digest),
        'runtime': _normalize_runtime(runtime),
        'versions': dict(versions) if versions else {},
        'env_keys': sorted(present_env_keys) if present_env_keys else []
    }
    
    # Generate canonical JSON (JCS-style: sorted keys, compact)
    canonical_json = json.dumps(
        fingerprint_obj, 
        sort_keys=True, 
        separators=(',', ':'), 
        ensure_ascii=False
    ).encode('utf-8')
    
    # Hash with BLAKE3 or SHA256
    if BLAKE3_AVAILABLE:
        fingerprint_hash = blake3.blake3(canonical_json).hexdigest()
        return f"b3:{fingerprint_hash}"
    else:
        fingerprint_hash = hashlib.sha256(canonical_json).hexdigest()
        return f"s256:{fingerprint_hash}"


def _normalize_runtime(runtime: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize runtime configuration for stable fingerprinting.
    
    Args:
        runtime: Runtime configuration dictionary
        
    Returns:
        Normalized runtime configuration
    """
    normalized = {}
    
    # Standard runtime fields
    if 'cpu' in runtime:
        normalized['cpu'] = float(runtime['cpu'])
    
    if 'memory' in runtime:
        normalized['memory'] = int(runtime['memory'])
    
    if 'gpu' in runtime:
        normalized['gpu'] = str(runtime['gpu'])
    
    if 'timeout' in runtime:
        normalized['timeout'] = int(runtime['timeout'])
    
    # Include any other fields in sorted order
    for key in sorted(runtime.keys()):
        if key not in normalized:
            normalized[key] = runtime[key]
    
    return normalized


def extract_env_keys(secrets: List[str], additional_keys: List[str] = None) -> List[str]:
    """
    Extract environment variable keys that should be included in fingerprint.
    
    Args:
        secrets: List of secret names that were resolved
        additional_keys: Additional environment keys to include
        
    Returns:
        Sorted list of environment variable names
    """
    env_keys = []
    
    # Add secret names
    if secrets:
        env_keys.extend(secrets)
    
    # Add additional keys
    if additional_keys:
        env_keys.extend(additional_keys)
    
    # Return sorted unique list
    return sorted(set(env_keys))


def compose_simple_fingerprint(
    image_digest: str,
    cpu: float = 1.0,
    memory: int = 512,
    gpu: str = None,
    secrets: List[str] = None
) -> str:
    """
    Compose simple environment fingerprint for common use cases.
    
    Args:
        image_digest: Container image digest
        cpu: CPU allocation
        memory: Memory allocation in MB
        gpu: Optional GPU specification
        secrets: Optional list of secret names
        
    Returns:
        Environment fingerprint string
    """
    runtime = {
        'cpu': cpu,
        'memory': memory
    }
    
    if gpu:
        runtime['gpu'] = gpu
    
    return compose_env_fingerprint(
        image_digest=image_digest,
        runtime=runtime,
        versions={},
        present_env_keys=secrets or []
    )