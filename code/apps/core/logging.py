from __future__ import annotations
import contextvars
import json
import os
import sys
import time
import random
import typing as t

_ctx = contextvars.ContextVar("log_ctx", default=None)


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def bind(**fields):
    """Bind context fields for current execution trace."""
    ctx = dict(_ctx.get() or {})
    ctx.update({k: v for k, v in fields.items() if v is not None})
    _ctx.set(ctx)


def clear():
    """Clear context to prevent cross-execution leakage."""
    _ctx.set(None)


def _redact(s: str) -> str:
    """Apply redaction patterns to string using centralized redaction."""
    try:
        from libs.runtime_common.redaction import redact_msg

        return redact_msg(s)
    except ImportError:
        # Safe fallback - better to redact everything than leak secrets
        return "[REDACTED]"


def _sample(env_key: str, default: float = 0.0) -> bool:
    """Check if event should be sampled based on environment rate."""
    try:
        rate = float(os.getenv(env_key, default))
    except Exception:
        rate = default
    return random.random() < rate


def _log_stream():
    stream_name = (os.getenv("LOG_STREAM") or "stdout").lower()
    return sys.stderr if stream_name == "stderr" else sys.stdout


def log(level: str, event: str, **fields):
    """Emit structured JSON log event with context binding."""
    # Developer experience toggle - pretty output for local dev
    use_json = os.getenv("JSON_LOGS", "1").lower() not in ("0", "false", "no")

    stream = _log_stream()

    base = {
        "ts": _ts(),
        "level": level,
        "event": event,
        "service": os.getenv("SERVICE", "theory"),
        "env": os.getenv("APP_ENV", os.getenv("MODAL_ENVIRONMENT", "dev")),
        "version": os.getenv("RELEASE", ""),
    }
    base.update(_ctx.get() or {})

    # Apply redaction and field truncation
    for k, v in list(fields.items()):
        if isinstance(v, str):
            fields[k] = _redact(v)[:2000]  # Field truncation at 2000 chars
    base.update(fields)

    if use_json:
        json.dump(base, stream, separators=(",", ":"), sort_keys=True)
        stream.write("\n")
    else:
        # Pretty console output for development
        ctx_fields = " ".join(f"{k}={v}" for k, v in base.items() if k not in ("ts", "level", "event"))
        stream.write(f"[{base['level'].upper()}] {base['event']} {ctx_fields}\n")

    stream.flush()


def info(event: str, **fields):
    log("info", event, **fields)


def warn(event: str, **fields):
    log("warn", event, **fields)


def error(event: str, **fields):
    log("error", event, **fields)


def debug(event: str, **fields):
    """Debug events with volume control via LOG_SAMPLE_DEBUG."""
    if _sample("LOG_SAMPLE_DEBUG", 0.0):  # Default quiet CI
        log("debug", event, **fields)
