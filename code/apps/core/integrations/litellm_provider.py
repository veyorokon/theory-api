"""
LiteLLM unified provider for all LLM backends.

Server-side adapter wrapping litellm. Django-free by design.
"""

import os
import litellm
import logging
import time
from typing import Iterable, Any

from apps.core.llm import LLMReply
from apps.core.integrations.secret_resolver import resolve_secret

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


PLACEHOLDER_KEYS = {"", "placeholder", "fake", "test", "dummy", "mock"}


def _looks_real_key(val: str | None) -> bool:
    """Check if an API key looks real (non-empty and not a placeholder)."""
    v = (val or "").strip()
    return bool(v) and v.lower() not in PLACEHOLDER_KEYS


def select_litellm_runner(ci: bool = None, token_or_key: str = None):
    """
    Select LiteLLM runner based on environment.

    Args:
        ci: If True, use mock. If None, check CI/SMOKE env vars
        token_or_key: API key. If None, resolve from environment

    Returns:
        Callable runner matching ProviderRunner Protocol
    """
    from apps.core.integrations.types import ProcessorResult, OutputItem
    import json

    # Determine CI environment if not explicitly provided
    if ci is None:
        ci = os.getenv("CI") == "true" or os.getenv("SMOKE") == "true"

    # Check LLM_PROVIDER for explicit mock override
    provider = resolve_secret("LLM_PROVIDER") or "auto"
    if ci or provider.lower() == "mock":
        from .litellm_mock import run_llm as mock_run_llm

        def mock_runner(inputs: dict) -> ProcessorResult:
            result = mock_run_llm(inputs)
            # Convert mock LLM response to ProcessorResult
            outputs = []

            # Extract text from choices
            choices = result.get("choices", [])
            for i, choice in enumerate(choices):
                content = choice.get("message", {}).get("content", "")
                if content:
                    outputs.append(OutputItem(relpath=f"outputs/choice_{i}.txt", bytes_=content.encode("utf-8")))

            # Add full response
            outputs.append(
                OutputItem(
                    relpath="outputs/response.json", bytes_=json.dumps(result, separators=(",", ":")).encode("utf-8")
                )
            )

            # Extract usage
            usage = {}
            if "usage" in result:
                usage_data = result["usage"]
                usage = {
                    "tokens_input": float(usage_data.get("prompt_tokens", 0)),
                    "tokens_output": float(usage_data.get("completion_tokens", 0)),
                }

            return ProcessorResult(
                outputs=outputs,
                processor_info=f"litellm-mock/{result.get('model', 'unknown')}",
                usage=usage,
                extra={"mock": "true"},
            )

        return mock_runner

    # Resolve key if not provided
    if token_or_key is None:
        token_or_key = resolve_secret("OPENAI_API_KEY")

    if not _looks_real_key(token_or_key):
        if provider.lower() == "openai":
            from apps.core.errors import ERR_SECRET_MISSING

            raise RuntimeError(f"{ERR_SECRET_MISSING}: OPENAI_API_KEY required for LiteLLM")
        # Auto mode falls back to mock if no real key
        from .litellm_mock import run_llm as mock_run_llm

        def fallback_runner(inputs: dict) -> ProcessorResult:
            result = mock_run_llm(inputs)
            # Same conversion logic as mock above
            outputs = []

            choices = result.get("choices", [])
            for i, choice in enumerate(choices):
                content = choice.get("message", {}).get("content", "")
                if content:
                    outputs.append(OutputItem(relpath=f"outputs/choice_{i}.txt", bytes_=content.encode("utf-8")))

            outputs.append(
                OutputItem(
                    relpath="outputs/response.json", bytes_=json.dumps(result, separators=(",", ":")).encode("utf-8")
                )
            )

            usage = {}
            if "usage" in result:
                usage_data = result["usage"]
                usage = {
                    "tokens_input": float(usage_data.get("prompt_tokens", 0)),
                    "tokens_output": float(usage_data.get("completion_tokens", 0)),
                }

            return ProcessorResult(
                outputs=outputs,
                processor_info=f"litellm-fallback/{result.get('model', 'unknown')}",
                usage=usage,
                extra={"fallback": "true"},
            )

        return fallback_runner

    from .litellm_runner import run_llm as real_run_llm

    def real_runner(inputs: dict) -> ProcessorResult:
        result = real_run_llm(inputs)
        # Convert real LLM response to ProcessorResult
        outputs = []

        # Extract text from choices
        choices = result.get("choices", [])
        for i, choice in enumerate(choices):
            content = choice.get("message", {}).get("content", "")
            if content:
                outputs.append(OutputItem(relpath=f"outputs/choice_{i}.txt", bytes_=content.encode("utf-8")))

        # Add full response
        outputs.append(
            OutputItem(
                relpath="outputs/response.json", bytes_=json.dumps(result, separators=(",", ":")).encode("utf-8")
            )
        )

        # Extract usage
        usage = {}
        if "usage" in result:
            usage_data = result["usage"]
            usage = {
                "tokens_input": float(usage_data.get("prompt_tokens", 0)),
                "tokens_output": float(usage_data.get("completion_tokens", 0)),
            }

        return ProcessorResult(
            outputs=outputs,
            processor_info=f"litellm/{result.get('model', 'unknown')}",
            usage=usage,
            extra={"provider": "openai"},
        )

    return real_runner
