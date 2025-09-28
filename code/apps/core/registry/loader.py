"""Lightweight registry loader for per-processor registry.yaml files.

New layout:
  code/apps/core/processors/<ns>_<name>/registry.yaml

Functions mirror the old interface used across the codebase to ease migration.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List


def _root_dir() -> Path:
    # .../code/apps/core/registry/loader.py -> .../code
    return Path(__file__).resolve().parents[3]


def _registry_yaml_path_for_ref(ref: str) -> Path:
    try:
        ns, rest = ref.split("/", 1)
        name, _ver = rest.split("@", 1)
    except ValueError as e:  # pragma: no cover
        raise FileNotFoundError(f"invalid ref '{ref}', expected ns/name@ver") from e

    return _root_dir() / "apps" / "core" / "processors" / f"{ns}_{name}" / "registry.yaml"


def load_processor_spec(ref: str) -> Dict:
    """Load registry.yaml for a single processor ref."""
    path = _registry_yaml_path_for_ref(ref)
    if not path.exists():
        raise FileNotFoundError(f"registry spec not found for {ref} at {path}")
    try:
        import yaml  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError("PyYAML required to load registry specs") from e
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def snapshot_for_ref(ref: str) -> Dict:
    """Compatibility shim: return {"processors": {ref: spec}}."""
    return {"processors": {ref: load_processor_spec(ref)}}


def get_registry_dir() -> str:
    """Compatibility shim for callers expecting a directory path.

    Historically returned '.../apps/core/registry/processors'. In the new layout
    there is no single directory; callers should not rely on this. We return the
    processors root to keep tools working: '.../apps/core/processors'.
    """
    return str(_root_dir() / "apps" / "core" / "processors")


def get_secrets_present_for_spec(spec: Dict) -> List[str]:
    """Extract which declared secrets are present in the current environment."""
    secrets = spec.get("secrets") or {}
    req = list(secrets.get("required", []) if isinstance(secrets, dict) else (secrets or []))
    names = sorted({n for n in (req or []) if n and n in os.environ})
    return names
