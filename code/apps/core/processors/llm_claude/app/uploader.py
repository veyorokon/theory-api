import requests
import json
import io
import time
from typing import List, Dict, Optional

_sess = requests.Session()


def put_object(
    put_url: str, fp: io.BytesIO, *, content_type: str | None = None, retries: int = 3, timeout: int = 30
) -> str:
    data = fp.getvalue()
    headers = {}
    if content_type:
        headers["Content-Type"] = content_type
    backoff = 0.2
    for i in range(retries):
        r = _sess.put(put_url, data=data, headers=headers, timeout=timeout)
        if 200 <= r.status_code < 300:
            return (r.headers.get("ETag") or "").strip('"')
        if r.status_code in (401, 403) and i < retries - 1:
            time.sleep(backoff)
            backoff *= 2
            continue
        r.raise_for_status()
    raise RuntimeError("unreachable")


def ensure_outputs_json(outputs: List[Dict]) -> bytes:
    outs = sorted(outputs, key=lambda o: o.get("path", ""))
    return json.dumps({"outputs": outs}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
