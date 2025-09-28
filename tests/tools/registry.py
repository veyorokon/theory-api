# tests/tools/registry.py
from __future__ import annotations
import pathlib
from typing import Iterator, Tuple, Dict, Iterable
import yaml


def each_processor_spec() -> Iterator[Dict]:
    """Yield processor spec dicts from embedded registry.yaml files."""
    root = pathlib.Path(__file__).resolve().parents[2]  # repo/
    processors_dir = root / "code" / "apps" / "core" / "processors"

    for processor_dir in sorted(processors_dir.iterdir()):
        if not processor_dir.is_dir():
            continue

        registry_file = processor_dir / "registry.yaml"
        if not registry_file.exists():
            continue

        try:
            spec = yaml.safe_load(registry_file.read_text(encoding="utf-8")) or {}
            # Add ref from directory name (ns_name -> ns/name@1)
            dir_name = processor_dir.name
            if "_" in dir_name:
                ns, name = dir_name.split("_", 1)
                spec["ref"] = f"{ns}/{name}@1"
            yield spec
        except Exception:
            # Skip invalid YAML files
            continue


def required_secrets() -> set[str]:
    s: set[str] = set()
    for spec in each_processor_spec():
        for name in (spec.get("secrets") or {}).get("required", []) or []:
            if isinstance(name, str) and name:
                s.add(name)
    return s


# ---------- Interface normalizers ----------
# Existing exports remain; add normalizers so callers don't care about tuple-vs-dict forms.


def iter_specs() -> Iterable[Dict]:
    """
    Yield processor spec dicts from embedded registries.
    """
    try:
        for spec in each_processor_spec():
            yield spec
    except Exception:
        # If registry loading fails, yield nothing (tests can handle empty iteration)
        return


def iter_mockable_refs() -> Iterable[str]:
    """Yield processor refs that declare supports_mock=True."""
    for spec in iter_specs():
        if spec.get("supports_mock") is True:
            yield spec["ref"]
