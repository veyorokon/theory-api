from __future__ import annotations
import unicodedata
import urllib.parse
import re

from dataclasses import dataclass
from typing import Iterable, Literal, TypedDict

FORBIDDEN_SEGMENTS = {".git", ".well-known"}
MAX_PATH_LEN = 1024
MAX_SEG_LEN = 255


class Selector(TypedDict):
    """A write selector scoped to a WorldPath.

    kind: "exact" targets a single path; "prefix" targets a subtree.
    path: canonical or raw WorldPath (will be canonicalized by helpers).
    """

    kind: Literal["exact", "prefix"]
    path: str


def _single_percent_decode(s: str) -> str:
    # reject raw %2f/%2F attempts before decode
    if re.search(r"%2[fF]", s):
        raise ValueError("forbidden percent-encoded slash")
    t = urllib.parse.unquote(s)
    if "/" in t:
        # decoded slash reintroduced
        raise ValueError("decoded slash forbidden")
    return t


def canonicalize_path(p: str) -> str:
    p = unicodedata.normalize("NFC", p)
    if len(p) > MAX_PATH_LEN:
        raise ValueError("path too long")
    parts = [seg for seg in p.split("/") if seg not in ("", ".", "..")]
    parts = [_single_percent_decode(seg) for seg in parts]
    if any(len(seg) > MAX_SEG_LEN for seg in parts):
        raise ValueError("segment too long")
    if any(seg in FORBIDDEN_SEGMENTS for seg in parts[1:]):
        raise ValueError("forbidden segment")
    # existing facet/root checks
    if not parts:
        raise ValueError("empty path after normalization")
    allowed = {"plan", "artifacts", "streams", "scratch"}
    facet = parts[0]
    if facet not in allowed:
        raise ValueError(f"Invalid facet: {facet}")
    return "/" + "/".join(parts)


# Remove parse_world_path - not needed for facet-root paths


def canonicalize_selector(sel: Selector) -> Selector:
    """Canonicalize selector with trailing slash enforcement.

    exact → no trailing slash
    prefix → must end with slash
    """
    base = canonicalize_path(sel["path"])
    if sel["kind"] == "exact":
        base = base.rstrip("/")
        if base == "":
            raise ValueError("exact selector cannot be root")
    elif sel["kind"] == "prefix":
        base = base if base.endswith("/") else base + "/"
    else:
        raise ValueError("Unknown selector kind")
    return {"kind": sel["kind"], "path": base}


def paths_overlap(a: str, b: str) -> bool:
    """Return True if two paths overlap (path-only check).

    Plan scoping will be handled by API callers.
    """
    a_c = canonicalize_path(a)
    b_c = canonicalize_path(b)
    return a_c == b_c or a_c.startswith(b_c + "/") or b_c.startswith(a_c + "/")


def selectors_overlap(sa: Selector, sb: Selector) -> bool:
    """Check if two selectors overlap (path-only)."""
    A, B = canonicalize_selector(sa), canonicalize_selector(sb)
    ap, bp = A["path"], B["path"]
    ak, bk = A["kind"], B["kind"]

    if ak == "exact" and bk == "exact":
        return ap == bp
    if ak == "exact" and bk == "prefix":
        return ap.startswith(bp)
    if ak == "prefix" and bk == "exact":
        return bp.startswith(ap)
    # prefix vs prefix: ancestor/descendant
    return ap.startswith(bp) or bp.startswith(ap)


def any_overlap(selectors_a: Iterable[Selector], selectors_b: Iterable[Selector]) -> bool:
    """Check if any selectors overlap (path-only; plan scoping handled by API callers)."""
    ws = [canonicalize_selector(s) for s in selectors_a]
    hs = [canonicalize_selector(s) for s in selectors_b]
    return any(selectors_overlap(a, b) for a in ws for b in hs)


@dataclass(frozen=True)
class LeaseHandle:
    """Handle for acquired lease with plan scoping."""

    id: str
    plan_id: str
    selectors: tuple[Selector, ...]
    reason: str | None = None


class LeaseManager:
    """Flag-gated, no-op façade for future lease enforcement."""

    def __init__(self, *, enabled: bool = False):
        self.enabled = enabled

    def acquire(self, plan_id: str, selectors: Iterable[Selector], *, reason: str | None = None) -> LeaseHandle:
        """Acquire lease handle with plan scoping."""
        sels = tuple(canonicalize_selector(s) for s in selectors)
        if self.enabled:
            # naive overlap check within the same request set
            for i, a in enumerate(sels):
                for b in sels[i + 1 :]:
                    if selectors_overlap(a, b):
                        raise ValueError(f"overlapping selectors in request: {a} vs {b}")
            # façade: no global registry; just pretend success
        # return a handle; id can be deterministic for tests
        sel_str = str(sorted((s["kind"], s["path"]) for s in sels))
        hid = f"lease:{plan_id}:{hash(sel_str) & 0xFFFFFFFF:x}"
        return LeaseHandle(id=hid, plan_id=plan_id, selectors=sels, reason=reason)

    def release(self, handle: LeaseHandle) -> None:
        """Release lease handle (no-op)."""
        return None

    def __call__(self, plan_id: str, selectors: Iterable[Selector], *, reason: str | None = None):
        """Context manager sugar for acquire/release."""
        handle = self.acquire(plan_id, selectors, reason=reason)

        class _Ctx:
            def __enter__(self_nonlocal):
                return handle

            def __exit__(self_nonlocal, exc_type, exc, _tb):
                self.release(handle)

        return _Ctx()
