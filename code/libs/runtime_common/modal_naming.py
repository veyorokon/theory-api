# libs/runtime_common/modal_naming.py
"""
Pure utility for Modal app naming - no Django dependencies.
One canonical naming function used by deploy, lookup, and Modal app.
"""

from __future__ import annotations
import re


def _slug(s: str) -> str:
    """Normalize string to valid app name component."""
    s = s.strip().lower()
    return re.sub(r"[^a-z0-9\-]+", "-", s)


def parse_ref(ref: str) -> tuple[str, str, int]:
    """Parse processor ref 'ns/name@v' where v is integer."""
    if "@" not in ref or "/" not in ref:
        raise ValueError("invalid processor ref")

    ns_name, ver = ref.split("@", 1)
    if "/" not in ns_name:
        raise ValueError("invalid processor ref")

    ns, name = ns_name.split("/", 1)
    if not ver.isdigit():
        raise ValueError("invalid version")

    return _slug(ns), _slug(name), int(ver)


def processor_slug(ref: str) -> str:
    """Convert ref to canonical processor slug: 'ns-name-vX'."""
    ns, name, ver = parse_ref(ref)
    return f"{ns}-{name}-v{ver}"


def modal_app_name(ref: str, *, env: str, branch: str | None = None, user: str | None = None) -> str:
    """
    Return Modal App name for a processor ref under an environment.

    dev:          <branch>-<user>-<ns>-<name>-vX
    staging/main: <ns>-<name>-vX
    """
    base = processor_slug(ref)
    env = (env or "").strip().lower()

    if env == "dev":
        if not branch or not user:
            raise ValueError("dev naming requires branch and user")
        return f"{_slug(branch)}-{_slug(user)}-{base}"

    return base  # staging/main
