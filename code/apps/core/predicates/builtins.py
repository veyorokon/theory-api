"""
Built-in predicate implementations.

Pure functions that evaluate conditions for plan execution.
Must be deterministic, fast, and return boolean values.
"""

import json
import os
import subprocess
import unicodedata
from pathlib import Path
from typing import Dict, Any, Optional
from urllib.parse import unquote

import jsonschema


def canon_path_facet_root(path: str) -> str:
    """
    Canonicalize path with facet-root validation.
    
    - Lowercase, percent-decode once (reject encoded slashes)
    - Unicode NFC normalization
    - Collapse double slashes
    - Forbid . and .. segments
    - Enforce facet root (/artifacts or /streams)
    
    Args:
        path: Raw path to canonicalize
        
    Returns:
        Canonical path
        
    Raises:
        ValueError: If path is invalid
    """
    # Reject encoded slashes (case-insensitive)
    if '%2f' in path.lower():
        raise ValueError('Encoded slashes not allowed in paths')
    
    # Percent-decode once
    path = unquote(path)
    
    # Unicode NFC normalization
    path = unicodedata.normalize('NFC', path)
    
    # Lowercase
    path = path.lower()
    
    # Ensure starts with /
    if not path.startswith('/'):
        path = '/' + path
    
    # Collapse double slashes
    while '//' in path:
        path = path.replace('//', '/')
    
    # Split and validate segments
    segments = path.split('/')
    clean_segments = []
    
    for seg in segments:
        if seg in ('.', '..'):
            raise ValueError(f'Path segments . and .. are forbidden: {seg}')
        if seg:  # Skip empty segments
            clean_segments.append(seg)
    
    # Validate facet root
    if not clean_segments:
        raise ValueError('Path must have at least one segment')
    
    facet = clean_segments[0]
    if facet not in ('artifacts', 'streams'):
        raise ValueError(f'Path must start with /artifacts or /streams, got: /{facet}')
    
    # Reconstruct canonical path
    return '/' + '/'.join(clean_segments)


def artifact_read_json(path: str) -> Optional[Dict[str, Any]]:
    """
    Read JSON artifact from storage.
    
    Args:
        path: Canonical path to artifact
        
    Returns:
        Parsed JSON dict or None if not found/invalid
    """
    from apps.storage.service import storage_service
    
    try:
        # Use storage service (not direct filesystem)
        content = storage_service.read_file(path)
        if not content:
            return None
        
        return json.loads(content.decode('utf-8'))
    except Exception:
        return None


def series_watermark_idx(prefix_path: str) -> int:
    """
    Get series watermark index.
    
    Flag-guarded stub - returns 0 if series models not present.
    Chat 0014 will wire actual streams.
    
    Args:
        prefix_path: Series prefix path
        
    Returns:
        Current watermark index (0 if not implemented)
    """
    # Check if ArtifactSeries model exists
    try:
        from apps.artifacts.models import ArtifactSeries
        
        # Query for series watermark
        series = ArtifactSeries.objects.filter(
            path__startswith=prefix_path
        ).order_by('-watermark_idx').first()
        
        return series.watermark_idx if series else 0
    except (ImportError, Exception):
        # Model not present or error - return 0
        return 0


def artifact_exists(path: str) -> bool:
    """
    Check if artifact exists at the given path.
    
    Args:
        path: Path to check (will be canonicalized)
        
    Returns:
        True if artifact exists, False otherwise
    """
    from apps.storage.service import storage_service
    
    try:
        # Canonicalize path
        canonical_path = canon_path_facet_root(path)
        
        # Use storage service to stat (no local FS, no network)
        return storage_service.file_exists(canonical_path)
    except (ValueError, Exception):
        # Invalid path or any error means artifact doesn't exist
        return False


def series_has_new(path: str, min_idx: int) -> bool:
    """
    Check if series has new items after the given index.
    
    Uses Truth counter via series_watermark_idx accessor.
    Returns False if model not present (0014 will wire streams).
    
    Args:
        path: Series path (will be canonicalized)
        min_idx: Minimum index to check after
        
    Returns:
        True if series has items with index > min_idx
    """
    try:
        # Canonicalize path
        canonical_path = canon_path_facet_root(path)
        
        # Get current watermark from Truth (or 0 if not wired)
        current_idx = series_watermark_idx(canonical_path)
        
        # Check if we have new items
        return current_idx > min_idx
    except (ValueError, Exception):
        # Invalid path or error - no new items
        return False


def json_schema_ok(path: str, schema_ref: str) -> bool:
    """
    Validate JSON at path against a schema.
    
    Args:
        path: Path to JSON artifact (will be canonicalized)
        schema_ref: Reference to schema (key in registry or path)
        
    Returns:
        True if JSON validates against schema, False otherwise
    """
    try:
        # Canonicalize path
        canonical_path = canon_path_facet_root(path)
        
        # Load JSON artifact via storage
        data = artifact_read_json(canonical_path)
        if data is None:
            return False
        
        # Resolve schema via registry wrapper
        schema = None
        
        # First check if it's in the generated schemas registry
        schema_registry_path = Path('docs/_generated/schemas.json')
        if schema_registry_path.exists():
            with open(schema_registry_path, 'r') as f:
                schemas = json.load(f)
                
            if schema_ref in schemas:
                schema = schemas[schema_ref]
        
        # If not found in registry, try as file path
        if schema is None:
            schema_file = Path(schema_ref)
            if schema_file.exists():
                with open(schema_file, 'r') as f:
                    schema = json.load(f)
            else:
                # Schema not found
                return False
        
        # Validate using jsonschema
        jsonschema.validate(instance=data, schema=schema)
        return True
        
    except (ValueError, json.JSONDecodeError, jsonschema.ValidationError, Exception):
        # Log reason would be done by caller; predicate returns bool only
        return False


def tests_pass(path_or_glob: str, timeout_ms: int = 5000) -> bool:
    """
    Run tests and check if they pass.
    
    Invokes pytest on the specified path/pattern with a timeout.
    Must be hermetic - no network calls.
    Path must be under sandbox root.
    
    Args:
        path_or_glob: Path or glob pattern for tests (under /artifacts/<plan>/tests/)
        timeout_ms: Timeout in milliseconds
        
    Returns:
        True if all tests pass (exit code 0), False otherwise
    """
    try:
        # Validate sandbox constraint — require facet-root sandbox path
        # Default sandbox root: /artifacts/<plan>/tests/
        if not path_or_glob.startswith('/artifacts/'):
            # Not in sandbox - reject
            return False
        
        # Convert timeout to seconds
        timeout_sec = timeout_ms / 1000.0
        
        # Build pytest command
        # Use -q for quiet, --disable-warnings to reduce output
        cmd = [
            'pytest',
            '-q',
            '--disable-warnings',
            '--tb=no',
            '--no-header',
            '--no-summary',
            path_or_glob
        ]
        
        # Run with timeout and capture output
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            cwd='code',  # Run from code directory
            env={
                **os.environ,
                # Ensure hermetic - no network
                'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1',
                'DJANGO_SETTINGS_MODULE': 'backend.settings.test',
            }
        )
        
        # Return True iff exit code is 0
        return result.returncode == 0
        
    except subprocess.TimeoutExpired:
        # Timeout means tests didn't complete
        return False
    except Exception:
        # Any other error means failure
        return False
