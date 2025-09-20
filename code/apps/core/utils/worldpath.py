# apps/core/utils/worldpath.py
from __future__ import annotations
import unicodedata
from typing import Tuple
from urllib.parse import unquote_to_bytes

# Path constraints
MAX_PATH_LEN = 1024
MAX_SEG_LEN = 255
FORBIDDEN_SEGMENTS = {".git", ".well-known"}

# Public error codes (keep these EXACT for tests/docs)
ERR_DECODED_SLASH = "ERR_DECODED_SLASH"
ERR_DOT_SEGMENTS = "ERR_DOT_SEGMENTS"
ERR_BAD_FACET = "ERR_BAD_FACET"
ERR_PERCENT_DECODE = "ERR_PERCENT_DECODE"
ERR_SELECTOR_KIND_MISMATCH = "ERR_SELECTOR_KIND_MISMATCH"
ERR_PATH_TOO_LONG = "ERR_PATH_TOO_LONG"
ERR_SEGMENT_TOO_LONG = "ERR_SEGMENT_TOO_LONG"
ERR_FORBIDDEN_SEGMENT = "ERR_FORBIDDEN_SEGMENT"


def _percent_decode_once(s: str) -> Tuple[str, str | None]:
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


def canonicalize_worldpath(path: str) -> Tuple[str, str | None]:
    """
    Canonicalize an absolute WorldPath. Rules:
      - Leading '/' required
      - NFC normalize
      - Percent-decode once; forbid decoded '/'
      - Collapse '//' runs
      - Forbid '.' and '..' segments
      - Only /artifacts/** or /streams/**
      - Enforce max path and segment lengths
      - Forbid dangerous segments
      - Return (normalized_path, error or None)
    """
    if not path or path[0] != "/":
        return path, ERR_BAD_FACET

    # Check total path length
    if len(path) > MAX_PATH_LEN:
        return path, ERR_PATH_TOO_LONG

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

    # Check segment lengths and forbidden segments
    for seg in segs:
        if seg and len(seg) > MAX_SEG_LEN:
            return path, ERR_SEGMENT_TOO_LONG
        if seg in FORBIDDEN_SEGMENTS:
            return path, ERR_FORBIDDEN_SEGMENT

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


def enforce_selector_kind(path: str, *, kind: str) -> Tuple[str, str | None]:
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
