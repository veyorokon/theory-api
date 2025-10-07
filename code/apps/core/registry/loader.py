"""Lightweight registry loader for tool registry.yaml files.

New layout (settings-driven):
  TOOLS_ROOTS = [/path/to/tools]
  Structure: <root>/<ns>/<name>/<ver>/registry.yaml

Functions mirror the old processor interface for backward compatibility.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List


def _get_tool_roots() -> List[Path]:
    """Get tool roots from Django settings."""
    try:
        from django.conf import settings

        return list(settings.TOOLS_ROOTS)
    except Exception:
        # Fallback for non-Django contexts (tests, scripts)
        root = Path(__file__).resolve().parents[5] / "tools"
        return [root]


def _registry_yaml_path_for_ref(ref: str) -> Path:
    """Resolve registry.yaml path for a tool ref.

    Searches TOOLS_ROOTS for pattern: <ns>/<name>/<ver>/registry.yaml
    Returns first match or raises FileNotFoundError.
    """
    try:
        ns, rest = ref.split("/", 1)
        name, ver = rest.split("@", 1)
    except ValueError as e:
        raise FileNotFoundError(f"invalid ref '{ref}', expected ns/name@ver") from e

    for root in _get_tool_roots():
        path = root / ns / name / ver / "registry.yaml"
        if path.exists():
            return path

    raise FileNotFoundError(f"registry spec not found for {ref} in TOOLS_ROOTS")


def load_processor_spec(ref: str) -> Dict:
    """Load registry.yaml for a single processor ref."""
    path = _registry_yaml_path_for_ref(ref)
    try:
        import yaml  # type: ignore
    except Exception as e:
        raise RuntimeError("PyYAML required to load registry specs") from e
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def snapshot_for_ref(ref: str) -> Dict:
    """Compatibility shim: return {"processors": {ref: spec}}."""
    return {"processors": {ref: load_processor_spec(ref)}}


def get_registry_dir() -> str:
    """Compatibility shim for callers expecting a directory path.

    Returns first TOOLS_ROOT to keep tools working.
    """
    roots = _get_tool_roots()
    return str(roots[0]) if roots else ""


def list_processor_refs() -> List[str]:
    """List all available tool refs from registry.yaml files.

    Scans all TOOLS_ROOTS for pattern: <ns>/<name>/<ver>/registry.yaml
    Returns refs like ["llm/litellm@1", "replicate/generic@1"].

    This is the canonical way to discover tools - used by:
    - LocalWsAdapter for stable port allocation
    - drift_audit.py for Modal deployment verification
    - Any other tooling that needs to enumerate tools
    """
    refs = []

    for root in _get_tool_roots():
        if not root.exists():
            continue

        # Pattern: <ns>/<name>/<ver>/registry.yaml
        for registry_path in sorted(root.glob("**/registry.yaml")):
            try:
                import yaml

                with registry_path.open("r", encoding="utf-8") as f:
                    spec = yaml.safe_load(f) or {}
                    ref = spec.get("ref")
                    if ref:
                        refs.append(ref)
            except Exception:
                continue

    return refs


def get_secrets_present_for_spec(spec: Dict) -> List[str]:
    """Extract which declared secrets are present in the current environment."""
    secrets = spec.get("secrets") or {}
    req = list(secrets.get("required", []) if isinstance(secrets, dict) else (secrets or []))
    names = sorted({n for n in (req or []) if n and n in os.environ})
    return names
