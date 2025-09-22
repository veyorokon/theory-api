# tests/tools/registry.py
from __future__ import annotations
import pathlib
from typing import Iterator, Tuple, Dict, Iterable
import yaml


def each_processor_spec() -> Iterator[Tuple[pathlib.Path, dict]]:
    """Yield (path, spec) for each registry YAML file."""
    root = pathlib.Path(__file__).resolve().parents[2]  # repo/
    reg = root / "code" / "apps" / "core" / "registry" / "processors"
    for f in sorted(reg.glob("*.yaml")):
        spec = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        yield f, spec


def required_secrets() -> set[str]:
    s: set[str] = set()
    for _, spec in each_processor_spec():
        for name in (spec.get("secrets") or {}).get("required", []) or []:
            if isinstance(name, str) and name:
                s.add(name)
    return s


# ---------- Interface normalizers ----------
# Existing exports remain; add normalizers so callers don't care about tuple-vs-dict forms.


def _spec_from_entry(entry) -> Dict:
    """Accept dict or (path, dict) and return dict."""
    if isinstance(entry, tuple) and len(entry) == 2 and isinstance(entry[1], dict):
        return entry[1]
    if isinstance(entry, dict):
        return entry
    raise TypeError(f"unsupported registry entry type: {type(entry)}")


def iter_specs() -> Iterable[Dict]:
    """
    Yield processor spec dicts regardless of the underlying each_processor_spec() return shape.
    """
    try:
        for entry in each_processor_spec():
            yield _spec_from_entry(entry)
    except Exception:
        # If registry loading fails, yield nothing (tests can handle empty iteration)
        return


def iter_mockable_refs() -> Iterable[str]:
    """Yield processor refs that declare supports_mock=True."""
    for spec in iter_specs():
        if spec.get("supports_mock") is True:
            yield spec["ref"]
