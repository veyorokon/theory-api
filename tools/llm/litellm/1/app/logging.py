import json
import os
import sys
import time


def _ts():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _stream():
    return sys.stderr if (os.getenv("LOG_STREAM", "stderr").lower() == "stderr") else sys.stdout


def info(event: str, **fields):
    rec = {
        "ts": _ts(),
        "level": "info",
        "event": event,
        "service": "processor",
        "env": os.getenv("APP_ENV", os.getenv("MODAL_ENVIRONMENT", "dev")),
    }
    rec.update(fields)
    json.dump(rec, _stream(), separators=(",", ":"), sort_keys=False)
    _stream().write("\n")
    _stream().flush()
