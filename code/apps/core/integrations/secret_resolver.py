import os


def resolve_secret(name: str) -> str | None:
    # Single entry-point: map registry secret names to env/material
    v = os.getenv(name) or os.getenv(name.upper())
    return v.strip() if v else None
