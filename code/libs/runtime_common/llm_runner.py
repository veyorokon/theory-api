"""Pure-Python LLM runner using LiteLLM (runtime-common)."""
from __future__ import annotations
import os
from typing import Any, Dict
from litellm import completion


def run_llm(inputs: Dict[str, Any], *, api_base: str | None = None, timeout_s: int | None = None) -> Dict[str, Any]:
    messages = inputs.get("messages", [])
    model = inputs.get("model", os.getenv("LITELLM_MODEL", "openai/gpt-4o-mini"))
    temperature = inputs.get("temperature", 0.7)
    max_tokens = inputs.get("max_tokens", 1000)

    kwargs: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if api_base:
        kwargs["api_base"] = api_base
    kwargs["timeout"] = int(timeout_s or os.getenv("LITELLM_TIMEOUT_S", "30"))

    resp = completion(**kwargs)

    content = ""
    usage = {}
    try:
        content = resp.choices[0].message.get("content", "")  # type: ignore[attr-defined]
        usage = resp.get("usage", {})  # type: ignore[call-arg]
    except Exception:
        content = getattr(getattr(resp, "choices", [{}])[0], "message", {}).get("content", "")
        u = getattr(resp, "usage", {})
        usage = u if isinstance(u, dict) else getattr(u, "__dict__", {})

    return {
        "status": "ok",
        "model": model,
        "response": content,
        "usage": {
            "prompt_tokens": usage.get("prompt_tokens", 0) or 0,
            "completion_tokens": usage.get("completion_tokens", 0) or 0,
            "total_tokens": usage.get("total_tokens", 0) or 0,
        },
    }

