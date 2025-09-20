# apps/core/processors/llm_litellm/provider.py
from __future__ import annotations
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping

# Import from runtime_common instead of defining locally
from libs.runtime_common.outputs import OutputItem


@dataclass
class ProcessorResult:
    outputs: List[OutputItem]
    processor_info: str
    usage: Mapping[str, float]
    extra: Mapping[str, Any]


# NOTE: no Django imports; this file lives entirely inside the processor image.


def _is_mock_mode(inputs: Dict[str, Any], config: Dict[str, Any]) -> bool:
    """
    Decide mock behavior:
    - explicit inputs["mode"] == "mock" -> mock
    - CI/SMOKE env hints can also force mock
    """
    if str(inputs.get("mode", "")).lower() == "mock":
        return True
    if os.getenv("CI") == "true" or os.getenv("SMOKE") == "true":
        # CI must never hit paid providers
        return True
    return False


def _coerce_messages(params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Accept several common shapes and normalize to OpenAI/LiteLLM-like messages:
      - params["messages"] already list -> return as-is
      - params["prompt"] string -> map to [{"role":"user","content": prompt}]
    """
    if isinstance(params.get("messages"), list):
        return params["messages"]
    prompt = params.get("prompt")
    if isinstance(prompt, str):
        return [{"role": "user", "content": prompt}]
    # Last resort: empty conversation (provider may error if truly required)
    return []


def _mock_response(model: str, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Deterministic, zero-egress mock payload shaped like a typical chat response.
    """
    last_user = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last_user = str(m.get("content", ""))
            break
    content = f"[mock:{model}] {last_user[:120]}"
    return {
        "id": "mock-llm-0000",
        "model": model,
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": content},
            }
        ],
        "usage": {
            "prompt_tokens": len(last_user) // 4,
            "completion_tokens": len(content) // 4,
            "total_tokens": (len(last_user) + len(content)) // 4,
        },
    }


def _normalize_usage(raw: Any) -> Dict[str, float]:
    """
    liteLLM returns provider-shaped usage; try to map a few common fields.
    """
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, float] = {}
    for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
        v = raw.get(k)
        if isinstance(v, (int, float)):
            out[k] = float(v)
    return out


def make_runner(config):
    """
    Factory returning a callable runner from ProviderConfig.
    """
    from libs.runtime_common.processor import ProviderConfig

    default_model = config.model or "gpt-4o-mini"
    mock_mode = config.mock

    def runner(inputs: Dict[str, Any]) -> ProcessorResult:
        # Inputs schema v1: {schema, model?, params, files?, mode?}
        model = str(inputs.get("model") or default_model)
        params = inputs.get("params") or {}
        messages = _coerce_messages(params)

        # Mock path (zero egress)
        if mock_mode or _is_mock_mode(inputs, {}):
            payload = _mock_response(model, messages)
            out = OutputItem(
                relpath="outputs/response.json",
                bytes_=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            )
            return ProcessorResult(
                outputs=[out],
                processor_info=f"llm_litellm:{model}",
                usage=_normalize_usage(payload.get("usage")),
                extra={"mock": "true"},
            )

        # Real path – import litellm only when needed (keeps processor import cheap)
        try:
            import litellm  # type: ignore
        except Exception as e:  # pragma: no cover
            # Let the processor/main transform this uncaught exception into an error envelope upstream
            raise RuntimeError("litellm not installed in this image") from e

        # Prepare API key (do not log)
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key.strip():
            # Surface as runtime error; outer layer (main/adapter) maps to error envelope
            raise RuntimeError("missing API key in OPENAI_API_KEY")

        # Call liteLLM (chat completions preferred; fallback to legacy)
        try:
            # Many liteLLM providers accept: completion() or chat.completions.create(...)
            # We try the chat path first; if not available, fallback gracefully.
            response = None
            if hasattr(litellm, "chat") and hasattr(litellm.chat, "completions"):
                response = litellm.chat.completions.create(model=model, messages=messages)
                # Normalize to dict (liteLLM may return pydantic-like objects)
                try:
                    payload = response.model_dump()  # pydantic objects
                except Exception:
                    payload = json.loads(json.dumps(response, default=lambda o: getattr(o, "__dict__", str(o))))
            else:
                # Legacy/simple completion path
                # litellm.completion(model="...", messages=[...]) also exists in some versions
                if hasattr(litellm, "completion"):
                    response = litellm.completion(model=model, messages=messages)
                    # Normalize to dict (same logic as chat path)
                    try:
                        payload = response.model_dump()  # pydantic objects
                    except Exception:
                        payload = json.loads(json.dumps(response, default=lambda o: getattr(o, "__dict__", str(o))))
                else:
                    # Last resort: raise a clear error
                    raise RuntimeError("Unsupported liteLLM version: no chat.completions or completion API")

            usage = _normalize_usage(getattr(response, "usage", None) if response is not None else payload.get("usage"))
            out = OutputItem(
                relpath="outputs/response.json",
                bytes_=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            )
            return ProcessorResult(
                outputs=[out],
                processor_info=f"llm_litellm:{model}",
                usage=usage,
                extra={},
            )
        except Exception as e:
            # Bubble up; processor main will surface as canonical error envelope via adapter
            raise

    return runner
