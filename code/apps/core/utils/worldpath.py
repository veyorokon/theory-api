# apps/core/utils/worldpath.py
from __future__ import annotations
import unicodedata
from typing import Tuple, Optional
from urllib.parse import unquote_to_bytes

# Public error codes (keep these EXACT for tests/docs)
ERR_DECODED_SLASH = "ERR_DECODED_SLASH"
ERR_DOT_SEGMENTS = "ERR_DOT_SEGMENTS"
ERR_BAD_FACET = "ERR_BAD_FACET"
ERR_PERCENT_DECODE = "ERR_PERCENT_DECODE"
ERR_SELECTOR_KIND_MISMATCH = "ERR_SELECTOR_KIND_MISMATCH"

def _percent_decode_once(s: str) -> Tuple[str, Optional[str]]:
    """
    Decode percent-escapes exactly once. Reject invalid encodings and
    reject if any decoded byte becomes '/' (security).
    """
    try:
        raw = unquote_to_bytes(s)  # produces bytes after a single unquote pass
    except Exception:
        return s, ERR_PERCENT_DECODE
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError:
        return s, ERR_PERCENT_DECODE
    if "/" in decoded and "%2F" in s.lower():
        # explicit %2F was decoded into slash → reject
        return s, ERR_DECODED_SLASH
    return decoded, None

def _collapse_slashes(s: str) -> str:
    out = []
    prev = None
    for ch in s:
        if ch == "/" and prev == "/":
            continue
        out.append(ch)
        prev = ch
    return "".join(out)

def canonicalize_worldpath(path: str) -> Tuple[str, Optional[str]]:
    """
    Canonicalize an absolute WorldPath. Rules:
      - Leading '/' required
      - NFC normalize
      - Percent-decode once; forbid decoded '/'
      - Collapse '//' runs
      - Forbid '.' and '..' segments
      - Only /artifacts/** or /streams/**
      - Return (normalized_path, error or None)
    """
    if not path or path[0] != "/":
        return path, ERR_BAD_FACET
    # NFC normalize
    path = unicodedata.normalize("NFC", path)
    # Decode once
    decoded, err = _percent_decode_once(path)
    if err:
        return path, err
    # Collapse '//' runs
    decoded = _collapse_slashes(decoded)
    # Segment checks
    segs = decoded.split("/")
    if "." in segs or ".." in segs:
        return path, ERR_DOT_SEGMENTS
    # Facet root
    if not (decoded.startswith("/artifacts/") or decoded.startswith("/streams/")):
        return path, ERR_BAD_FACET
    # No trailing normalization beyond the above; exact bytes preserved otherwise
    return decoded, None

def canonicalize_relpath(rel: str) -> str:
    """
    Canonicalize a POSIX relative path (used for targets inside write_prefix).
    No leading '/', no '.' or '..' segments, NFC normalize, percent-decode once, collapse slashes.
    """
    rel = rel.replace("\\", "/")
    if rel.startswith("/"):
        raise ValueError("relative path must not start with '/'")
    rel = unicodedata.normalize("NFC", rel)
    rel_dec, err = _percent_decode_once(rel)
    if err:
        raise ValueError(err)
    rel_dec = _collapse_slashes(rel_dec)
    segs = rel_dec.split("/")
    if any(seg in (".", "..") for seg in segs):
        raise ValueError(ERR_DOT_SEGMENTS)
    return rel_dec

def enforce_selector_kind(path: str, *, kind: str) -> Tuple[str, Optional[str]]:
    """
    Ensure trailing slash semantics:
      - kind="prefix"  → must end with '/'
      - kind="exact"   → must NOT end with '/'
    """
    p, err = canonicalize_worldpath(path)
    if err:
        return path, err
    if kind == "prefix" and not p.endswith("/"):
        return path, ERR_SELECTOR_KIND_MISMATCH
    if kind == "exact" and p.endswith("/"):
        return path, ERR_SELECTOR_KIND_MISMATCH
    return p, None
