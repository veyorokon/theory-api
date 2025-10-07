from __future__ import annotations

import contextvars
import json
import os
import random
import sys
import time
from typing import Any, Dict

# ---- context ---------------------------------------------------------------

_CTX = contextvars.ContextVar("log_ctx", default=None)


def bind(**fields: Any) -> None:
    """
    Bind context fields for the current execution trace.
    Use for things like execution_id, tool_ref, adapter, mode, etc.
    """
    ctx = dict(_CTX.get() or {})
    # Keep only non-None values; shallow copy is fine for flat fields
    ctx.update({k: v for k, v in fields.items() if v is not None})
    _CTX.set(ctx)


def clear() -> None:
    """Clear bound context to prevent cross-execution leakage (important in workers)."""
    _CTX.set(None)


# ---- internal utilities ----------------------------------------------------


def _ts() -> str:
    # UTC ISO8601 seconds resolution (stable & compact)
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _redact(s: str) -> str:
    """
    Apply central redaction. If redaction helper is unavailable,
    fall back to pattern-based redaction for common secrets.
    """
    try:
        from libs.runtime_common.redaction import redact_msg  # lazy import

        return redact_msg(s)
    except Exception:
        # Fallback: selective redaction for common secret patterns
        import re

        # Patterns for common secrets (case-insensitive)
        secret_patterns = [
            (r'(token|key|secret|password|auth|bearer|api[_-]?key)["\s:=]+([^\s"\']+)', r"\1=***"),
            (r"(sk|pk)[_-][a-zA-Z0-9]{20,}", r"***"),  # API keys like sk_live_...
            (r"Bearer\s+[a-zA-Z0-9\-._~+/]+=*", "Bearer ***"),  # Bearer tokens
        ]

        result = s
        for pattern, replacement in secret_patterns:
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)

        return result


def _sample(env_key: str, default: float = 0.0) -> bool:
    """Return True with probability defined by ENV var (e.g., LOG_SAMPLE_DEBUG=0.05)."""
    try:
        rate = float(os.getenv(env_key, default))
    except Exception:
        rate = default
    return random.random() < rate


def _stream():
    """
    Choose output stream. Default to stderr to preserve stdout purity.
    Override by setting LOG_STREAM=stdout|stderr.
    """
    from django.conf import settings

    stream_name = settings.LOG_CONFIG["STREAM"].lower()
    return sys.stdout if stream_name == "stdout" else sys.stderr


def _as_json(event: Dict[str, Any]) -> str:
    # Compact JSON, stable key order for easier diffs
    return json.dumps(event, separators=(",", ":"), sort_keys=True, ensure_ascii=False)


# ---- core logger -----------------------------------------------------------


def log(level: str, event: str, **fields: Any) -> None:
    """
    Emit a single structured log event to the configured stream
    (stderr by default). Honors:
      - LOG_STREAM (stderr|stdout)
      - JSON_LOGS (1/0)  -> pretty console output when disabled
      - LOG_SAMPLE_DEBUG (0.0..1.0) for debug throttling via debug()
    """
    from django.conf import settings

    # Build base shape
    base: Dict[str, Any] = {
        "ts": _ts(),
        "level": level,
        "event": event,
        "service": settings.LOG_CONFIG["SERVICE"],
        "env": settings.LOG_CONFIG["ENV"],
        "version": settings.LOG_CONFIG["RELEASE"],
    }

    # Merge bound context then fields (fields win)
    ctx = _CTX.get() or {}
    if ctx:
        base.update(ctx)

    # Redact long/secretful strings & cap field length for safety
    safe_fields: Dict[str, Any] = {}
    for k, v in fields.items():
        if isinstance(v, str):
            safe_fields[k] = _redact(v)[:2000]  # hard cap to contain explosions
        else:
            safe_fields[k] = v
    base.update(safe_fields)

    stream = _stream()
    json_mode = settings.LOG_CONFIG["JSON"]

    if json_mode:
        stream.write(_as_json(base) + "\n")
    else:
        # Dev-friendly pretty line (still single-line to keep grep-able)
        kv = " ".join(f"{k}={v}" for k, v in base.items() if k not in ("ts", "level", "event"))
        stream.write(f"[{base['level'].upper()}] {base['event']} {kv}\n")

    stream.flush()


def info(event: str, **fields: Any) -> None:
    log("info", event, **fields)


def warn(event: str, **fields: Any) -> None:
    log("warn", event, **fields)


def error(event: str, **fields: Any) -> None:
    log("error", event, **fields)


def debug(event: str, **fields: Any) -> None:
    """
    Debug events with volume control via LOG_SAMPLE_DEBUG (default 0.0).
    Example: LOG_SAMPLE_DEBUG=0.05 to sample ~5% of debug logs.
    """
    if _sample("LOG_SAMPLE_DEBUG", 0.0):
        log("debug", event, **fields)
