"""Mock LLM runner (runtime-common)."""
from __future__ import annotations
from typing import Any, Dict


def run_llm(inputs: Dict[str, Any]) -> Dict[str, Any]:
    messages = inputs.get("messages", [])
    model = inputs.get("model", "openai/gpt-4o-mini")
    if messages:
        last = messages[-1].get("content", "")
        text = f"Mock LLM response to: {last}"
    else:
        text = "Mock LLM response"
    return {
        "status": "ok",
        "model": model,
        "response": text,
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
        },
    }

