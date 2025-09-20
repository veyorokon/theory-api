from __future__ import annotations
import json
import time
from typing import Any, Dict, Callable
from libs.runtime_common.outputs import OutputItem
from libs.runtime_common.types import ProcessorResult
from libs.runtime_common.mode import resolve_mode, is_mock


def make_runner(config: Dict[str, Any]) -> Callable[[Dict[str, Any]], ProcessorResult]:
    """
    Returns a callable(inputs) -> ProcessorResult.
    - inputs expects: {"schema":"v1","model":"...","params":{...},"mode":"real|mock|smoke"}
    """
    # Late import to keep container deps local
    try:
        import litellm  # type: ignore
    except Exception:
        litellm = None

    def _runner(inputs: Dict[str, Any]) -> ProcessorResult:
        mode = resolve_mode(inputs)
        params = inputs.get("params", {}) or {}
        model = inputs.get("model")
        t0 = time.time()

        if is_mock(mode):
            payload = {
                "model": model or "mock-model",
                "choices": [{"message": {"role": "assistant", "content": "this is a mock reply"}}],
                "mode": mode,
            }
            out = [
                OutputItem(
                    relpath="outputs/response.json",
                    bytes_=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
                    mime="application/json",
                )
            ]
            return ProcessorResult(outputs=out, processor_info=f"litellm:{model}:{mode}", usage={}, extra={})

        if litellm is None:
            raise RuntimeError("litellm not installed in this container")

        # Call: prefer chat.completions if present; else fallback to completion()
        messages = params.get("messages")
        if hasattr(litellm, "chat") and hasattr(litellm.chat, "completions"):
            resp = litellm.chat.completions.create(model=model, messages=messages)  # OpenAI-like path
            payload = getattr(resp, "model_dump", lambda: resp)()
        else:
            resp = litellm.completion(model=model, messages=messages)  # legacy path
            payload = getattr(resp, "model_dump", lambda: resp)()

        usage = payload.get("usage", {})
        duration_ms = int((time.time() - t0) * 1000)

        out = [
            OutputItem(
                relpath="outputs/response.json",
                bytes_=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
                mime="application/json",
            )
        ]
        return ProcessorResult(
            outputs=out,
            processor_info=f"litellm:{model}:{mode}",
            usage={"duration_ms": duration_ms, **usage},
            extra={},
        )

    return _runner
