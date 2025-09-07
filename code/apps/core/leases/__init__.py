"""Leases façade package (Core).

Provides a flag-gated, no-op LeaseManager and helpers for canonicalizing
WorldPaths and detecting selector overlaps. Runtime enforcement will be
introduced later; this façade exists to stabilize call sites and tests.
"""

from .manager import (
    Selector,
    LeaseHandle,
    LeaseManager,
    canonicalize_path,
    canonicalize_selector,
    paths_overlap,
    selectors_overlap,
    any_overlap,
)

__all__ = [
    "Selector",
    "LeaseHandle",
    "LeaseManager",
    "canonicalize_path",
    "canonicalize_selector",
    "paths_overlap",
    "selectors_overlap",
    "any_overlap",
]

