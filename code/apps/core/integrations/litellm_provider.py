"""
LiteLLM unified provider for all LLM backends.

Server-side adapter wrapping litellm. Django-free by design.
"""
import litellm
import logging
import time
from typing import Iterable

from apps.core.llm import LLMReply

logger = logging.getLogger(__name__)


class LiteLLMProvider:
    """Unified LLM provider using LiteLLM substrate.
    
    Handles all providers through litellm.completion with consistent interface.
    """
    
    def __init__(self, model_default: str = "openai/gpt-4o-mini", api_base: str | None = None, timeout: int = 30):
        self.model_default = model_default
        self.timeout = timeout
        self._api_base = api_base.strip() if api_base else None
    
    def chat(self, prompt: str, *, model: str | None = None) -> LLMReply:
        m = model or self.model_default
        logger.info("litellm.start", extra={"model": m, "api_base": self._api_base})
        start_time = time.time()
        try:
            kwargs = {
                "model": m,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 512,
                "temperature": 0.0,
                "timeout": self.timeout,
            }
            if self._api_base:
                kwargs["api_base"] = self._api_base
            resp = litellm.completion(**kwargs)
        except Exception as e:
            error_msg = str(e).lower()
            if "openai" in m and ("api" in error_msg or "key" in error_msg):
                raise RuntimeError("OpenAI API error: set OPENAI_API_KEY") from e
            if "ollama" in m:
                if "connection" in error_msg or "refused" in error_msg:
                    raise RuntimeError(f"Ollama unreachable at {self._api_base or 'default host'}") from e
                if "model" in error_msg or "not found" in error_msg:
                    raise RuntimeError("Ollama model not found; pull it first") from e
            raise RuntimeError(f"LLM request failed: {e}") from e

        text = ""
        if hasattr(resp, "choices") and resp.choices:
            text = resp.choices[0].message.content.strip()
        latency_ms = int((time.time() - start_time) * 1000)
        raw_usage = {}
        if hasattr(resp, "usage"):
            raw_usage = resp.usage if isinstance(resp.usage, dict) else resp.usage.__dict__
        usage = {
            "tokens_in": int(raw_usage.get("prompt_tokens", 0) or 0),
            "tokens_out": int(raw_usage.get("completion_tokens", 0) or 0),
            "latency_ms": latency_ms,
            "usd_micros": 0,
        }
        logger.info("litellm.finish", extra={"model": m, "resp_len": len(text)})
        return LLMReply(text=text, provider="litellm", model=m, usage=usage)
    
    def stream_chat(self, prompt: str, *, model: str | None = None) -> Iterable[str]:
        m = model or self.model_default
        logger.info("litellm.stream_start", extra={"model": m, "api_base": self._api_base})
        kwargs = {
            "model": m,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
            "temperature": 0.0,
            "timeout": self.timeout,
        }
        if self._api_base:
            kwargs["api_base"] = self._api_base
        stream = litellm.completion(**kwargs)
        for chunk in stream:
            if hasattr(chunk, "choices") and chunk.choices:
                delta = chunk.choices[0].delta
                content = getattr(delta, "content", None)
                if content:
                    yield content

