from __future__ import annotations
import os
import yaml
from typing import Dict, List


def ref_to_yaml_filename(ref: str) -> str:
    """
    Map 'llm/litellm@1' -> 'llm_litellm.yaml'.
    Version suffix is ignored at file name level; the YAML can still contain '@1' in its 'name'.
    """
    base = ref.split("@", 1)[0]  # 'llm/litellm'
    fname = base.replace("/", "_") + ".yaml"
    return fname


def get_registry_dir() -> str:
    """Get the registry directory path."""
    return os.path.join(os.path.dirname(__file__), "processors")


def load_processor_spec(ref: str) -> Dict:
    """Load processor specification from registry YAML file."""
    registry_dir = get_registry_dir()
    path = os.path.join(registry_dir, ref_to_yaml_filename(ref))
    if not os.path.exists(path):
        raise FileNotFoundError(f"registry spec not found for {ref} at {path}")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def snapshot_for_ref(ref: str) -> Dict:
    """Create registry snapshot for a single processor reference."""
    spec = load_processor_spec(ref)
    return {"processors": {ref: spec}}


def _present_secret_names(required: List[str], optional: List[str]) -> List[str]:
    """Get list of secret names that are present in environment."""
    import os

    names = set()
    for n in required + optional:
        if n and n in os.environ:
            names.add(n)
    return sorted(names)


def get_secrets_present_for_spec(spec: Dict) -> List[str]:
    """Extract and check which secrets are present in environment for a processor spec."""
    required, optional = [], []
    secrets_section = spec.get("secrets")
    if isinstance(secrets_section, dict):
        required = list(secrets_section.get("required", []))
        optional = list(secrets_section.get("optional", []))
    elif isinstance(secrets_section, list):
        required = list(secrets_section)

    return _present_secret_names(required, optional)
