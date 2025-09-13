"""Django-free helpers for Modal app/function naming."""

from __future__ import annotations


def parse_slug_ver(processor_ref: str) -> tuple[str, str]:
    """Parse processor ref "ns/name@ver" into (slug, v<ver>)."""
    base, ver = (processor_ref.split("@", 1) + ["1"])[:2]
    slug = base.replace("/", "-").lower()
    ver_s = f"v{ver}" if not ver.startswith("v") else ver
    return slug, ver_s


def modal_app_name_from_ref(processor_ref: str, env: str) -> str:
    """Compute Modal app name for a processor ref and environment."""
    slug, ver = parse_slug_ver(processor_ref)
    return f"{slug}-{ver}-{env}"


def modal_fn_name() -> str:
    """Return the Modal function name for 0021."""
    return "run"
