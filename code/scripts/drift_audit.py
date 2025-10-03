#!/usr/bin/env python3
"""
Modal drift audit: checks that expected functions exist in the target environment.

For 0021, we validate presence by name (exec__{slug}__v{ver}).
In 0022 we can extend this to compare deployed image digests vs registry pins.

Exit code:
  0: no drift (all functions present)
  2: drift detected or unable to verify (treated as failure on main)
"""

from __future__ import annotations
import os
import sys
from pathlib import Path
import yaml


def ref_to_slug_ver(ref: str) -> tuple[str, str]:
    base, ver = ref.split("@", 1)
    slug = base.replace("/", "_")
    return slug, ver


def expected_apps(processors_root: Path, env: str) -> list[tuple[str, str, str]]:
    """Return list of (ref, app_name, func_name) using canonical processor discovery."""
    from apps.core.registry.loader import list_processor_refs

    out: list[tuple[str, str, str]] = []
    for ref in list_processor_refs():
        if not isinstance(ref, str) or "@" not in ref:
            continue
        slug, ver = ref_to_slug_ver(ref)
        app = f"{slug}-v{ver}-{env}"
        out.append((ref, app, "fastapi_app"))
    return out


def main() -> int:
    env = os.environ.get("MODAL_ENVIRONMENT") or "dev"
    app = os.environ.get("MODAL_APP_NAME", "theory-rt")
    base = Path(__file__).resolve().parents[1]
    processors_root = base / "apps/core/processors"

    try:
        import modal
    except Exception as e:
        print(f"[drift] ERROR: modal SDK import failed: {e}", file=sys.stderr)
        return 2

    # Build checks
    checks = expected_apps(processors_root, env)
    if not checks:
        print("[drift] WARNING: no registry processors found", file=sys.stderr)
        return 0

    problems: list[str] = []
    for ref, app_name, fn_name in checks:
        try:
            # Resolve by name in target environment
            modal.Function.from_name(app_name, fn_name, environment_name=env)
            print(f"[drift] OK: {ref} => {app_name}.{fn_name}")
        except Exception as e:
            problems.append(f"[drift] MISSING: {ref} => {app_name}.{fn_name}: {e}")

    if problems:
        for msg in problems:
            print(msg)
        print(f"[drift] Drift detected: {len(problems)} missing function(s)", file=sys.stderr)
        return 2

    print("[drift] No drift detected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
