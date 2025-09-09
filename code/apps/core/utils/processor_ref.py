"""
Processor reference utilities for path resolution.

Centralizes processor ref → local path resolution anchored to settings.BASE_DIR.
No environment-dependent behavior or CWD detection.
"""

from pathlib import Path
from django.conf import settings


def ref_to_local_dir(ref: str) -> str:
    """
    Convert processor reference to local directory name.
    
    Args:
        ref: Processor reference (e.g., 'llm/litellm@1')
        
    Returns:
        Local directory name (e.g., 'llm_litellm')
        
    Example:
        'llm/litellm@1' -> 'llm_litellm'
        'vision/ocr@2' -> 'vision_ocr'
    """
    # Strip version suffix and convert to directory name
    base = ref.split('@', 1)[0]
    return base.replace('/', '_')


def local_processor_path(ref: str) -> Path:
    """
    Get full local path to processor directory anchored to BASE_DIR.
    
    Args:
        ref: Processor reference
        
    Returns:
        Absolute path to processor directory
        
    Example:
        'llm/litellm@1' -> Path(settings.BASE_DIR) / 'apps/core/processors/llm_litellm'
    """
    return Path(settings.BASE_DIR) / 'apps' / 'core' / 'processors' / ref_to_local_dir(ref)


def registry_path(ref: str) -> Path:
    """
    Get path to processor registry YAML file.
    
    Args:
        ref: Processor reference
        
    Returns:
        Path to registry file
        
    Example:
        'llm/litellm@1' -> Path(settings.BASE_DIR) / 'apps/core/registry/processors/llm_litellm.yaml'
    """
    return Path(settings.BASE_DIR) / 'apps' / 'core' / 'registry' / 'processors' / f'{ref_to_local_dir(ref)}.yaml'