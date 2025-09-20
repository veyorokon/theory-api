from __future__ import annotations
import io
import json
import time
import urllib.request
from typing import Any, Dict, Callable, Iterable
from libs.runtime_common.outputs import OutputItem
from libs.runtime_common.types import ProcessorResult
from libs.runtime_common.mode import resolve_mode, is_mock


def _download(url: str, *, timeout: int = 20, max_bytes: int = 20_000_000) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 (trusted model CDN)
        data = resp.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise RuntimeError(f"asset too large (> {max_bytes} bytes)")
        return data


def _flatten_urls(obj: Any) -> Iterable[str]:
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _flatten_urls(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _flatten_urls(v)
    elif isinstance(obj, str) and obj.startswith(("http://", "https://")):
        yield obj


def make_runner(config: Dict[str, Any]) -> Callable[[Dict[str, Any]], ProcessorResult]:
    """
    Returns a callable(inputs) -> ProcessorResult.
    - inputs expects: {"schema":"v1","model":"owner/model:ver","params":{...},"mode":"real|mock|smoke"}
    """
    # Late import so Django app never depends on this SDK
    try:
        import replicate as _rep  # type: ignore
    except Exception:
        _rep = None

    def _runner(inputs: Dict[str, Any]) -> ProcessorResult:
        mode = resolve_mode(inputs)
        model = inputs.get("model")
        params = inputs.get("params", {}) or {}

        if is_mock(mode):
            payload = {"model": model or "mock-flux", "result": ["https://example.com/mock.webp"], "mode": mode}
            outputs = [
                OutputItem(
                    relpath="outputs/response.json",
                    bytes_=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
                    mime="application/json",
                )
            ]
            return ProcessorResult(
                outputs=outputs, processor_info=f"replicate:{model or 'unknown'}:{mode}", usage={}, extra={}
            )

        if _rep is None:
            raise RuntimeError("replicate SDK not installed in this container")

        t0 = time.time()
        client = _rep.Client()  # expects REPLICATE_API_TOKEN in env (inside container)
        result = client.run(model, input=params)

        # Serialize JSON payload first, then discover downloadable URLs in the serialized shape.
        serializable = {"result": result}
        resp_bytes = json.dumps(serializable, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

        outputs = [OutputItem(relpath="outputs/response.json", bytes_=resp_bytes, mime="application/json")]

        # Best-effort asset fetch (optional)
        for i, url in enumerate(_flatten_urls(serializable)):
            try:
                blob = _download(url)
            except Exception:
                continue  # swallow asset errors; response.json still present
            # Simple deterministic name
            rel = f"outputs/assets/{i:02d}.bin"
            # MIME detection left to storage pipeline (or extend if needed)
            outputs.append(OutputItem(relpath=rel, bytes_=blob, mime="application/octet-stream"))

        duration_ms = int((time.time() - t0) * 1000)
        return ProcessorResult(
            outputs=outputs,
            processor_info=f"replicate:{model}:{mode}",
            usage={"duration_ms": duration_ms},
            extra={},
        )

    return _runner
