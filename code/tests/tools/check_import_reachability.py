#!/usr/bin/env python3
"""
Import reachability test: fail if a module isn't reachable from entrypoints.

This catches orphan modules that nothing ever imports from real entry points.
Complements vulture (unused symbols) by detecting whole unused modules.
"""
import sys
from pathlib import Path
from grimp import build_graph

# Treat repo root as import root
ROOT = Path(__file__).resolve().parents[3]  # code/tests/tools -> code -> theory_api
sys.path.insert(0, str(ROOT / "code"))

ENTRYPOINTS = {
    # Real entry nodes the app starts from:
    "manage",                          # manage.py
    "modal_app",                      # code/modal_app.py
    "apps.core.adapters",             # adapter call sites
    "apps.core.management.commands",  # Django management commands
    "apps.runtime.services",          # orchestration services
    "backend.wsgi",                   # WSGI entry
    "backend.asgi",                   # ASGI entry
    "backend.urls",                   # URL routing entry
    "apps.core.registry.loader",      # registry loading
}

EXCLUDE_PATTERNS = (
    ".tests.",              # test modules (intentionally isolated)
    ".migrations.",         # Django migrations (loaded dynamically)
    "conftest",            # pytest configuration
    "validate_chat_",      # agent validation scripts (run manually)
)

def main() -> int:
    """Check for unreachable modules in the codebase."""
    try:
        g = build_graph(
            package_names=["apps", "backend", "libs"],  # top-level packages we own
            build_kwargs={"follow_links": True},
        )
    except Exception as e:
        print(f"Failed to build import graph: {e}")
        return 1

    # Nodes reachable from any entrypoint
    reachable = set()
    for ep in ENTRYPOINTS:
        try:
            downstream = g.find_downstream_modules(ep, include_self=True)
            reachable.update(downstream)
        except Exception:
            # Entrypoint might not exist or be importable, skip gracefully
            continue

    # Candidate dead modules: in our codebase but not reachable
    candidates = [
        n for n in g.modules
        if n.startswith(("apps.", "backend.", "libs."))
        and not any(pattern in n for pattern in EXCLUDE_PATTERNS)
        and n not in reachable
    ]

    # Heuristic ignore for packages that are intentionally optional
    ignored = [
        n for n in candidates 
        if (
            n.startswith("apps.core.processors.") and n.count('.') > 3 or  # processor internals
            n.endswith(("__main__", "settings.development", "settings.production"))  # conditional imports
        )
    ]
    
    dead = sorted(set(candidates) - set(ignored))

    if dead:
        print("🔍 Unreachable modules detected:")
        for module in dead:
            print(f"  ❌ {module}")
        print()
        print("💡 If these are dynamic entry points, add them to ENTRYPOINTS.")
        print("💡 If they're intentionally unused, add them to the ignored patterns.")
        return 1
    
    print(f"✅ All {len(g.modules)} modules are reachable from entry points")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())