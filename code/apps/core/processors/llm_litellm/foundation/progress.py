"""Progress and logging utilities."""
import json
import time

JSON_SEPARATORS = (",", ":")


def _now_ms() -> int:
    return int(time.time() * 1000)


def log(msg: str) -> None:
    """Log message with timestamp."""
    ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    print(f"[{ts}] {msg}", flush=True)


def progress(pct: float, **kw) -> None:
    """Emit NDJSON progress line for streaming (0022+)."""
    rec = {"kind": "progress", "pct": round(pct, 3), "ts_ms": _now_ms()}
    rec.update(kw)
    print(json.dumps(rec, separators=JSON_SEPARATORS), flush=True)