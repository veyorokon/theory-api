"""
LiteLLM unified provider for all LLM backends.

Supports OpenAI, Ollama, and 100+ other providers through a single interface.
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
        """Initialize LiteLLM provider.
        
        Args:
            model_default: Default model to use (e.g., "openai/gpt-4o-mini", "ollama/qwen3:0.6b")
            api_base: Optional API base URL (e.g., "http://127.0.0.1:11434" for Ollama)
            timeout: Request timeout in seconds
        """
        self.model_default = model_default
        self.timeout = timeout
        
        # IMPORTANT: never mutate global litellm.* state (test isolation + thread-safety)
        # Keep api_base on the instance and pass it per-request only.
        self._api_base = api_base.strip() if api_base else None
    
    def chat(self, prompt: str, *, model: str | None = None) -> LLMReply:
        """Generate a response using LiteLLM.
        
        Args:
            prompt: Input prompt for the model
            model: Model name (uses default if not specified)
            
        Returns:
            LLMReply with response text and metadata
            
        Raises:
            RuntimeError: With friendly error messages for common issues
        """
        m = model or self.model_default
        logger.info("litellm.start", extra={"model": m, "api_base": self._api_base})
        
        start_time = time.time()
        
        try:
            # Prepare request parameters
            kwargs = {
                "model": m,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 512,
                "temperature": 0.0,
                "timeout": self.timeout,
            }
            
            # Add api_base if specified (per-request isolation)
            if self._api_base:
                kwargs["api_base"] = self._api_base
            
            # Make the request
            resp = litellm.completion(**kwargs)
            
        except Exception as e:
            # Friendly error messages for common cases
            error_msg = str(e).lower()
            
            if "openai" in m and ("api" in error_msg or "key" in error_msg):
                raise RuntimeError(
                    f"OpenAI API error: OPENAI_API_KEY missing or invalid. "
                    f"Set OPENAI_API_KEY environment variable and retry."
                ) from e
            
            if "ollama" in m:
                if "connection" in error_msg or "refused" in error_msg:
                    raise RuntimeError(
                        f"Ollama daemon unreachable at {self._api_base or 'default host'}. "
                        f"Ensure 'ollama serve' is running and accessible."
                    ) from e
                elif "model" in error_msg or "not found" in error_msg:
                    model_name = m.replace("ollama/", "")
                    raise RuntimeError(
                        f"Ollama model '{model_name}' not found. "
                        f"Pull it with: ollama pull {model_name}"
                    ) from e
            
            # Re-raise original error if not a known case
            raise RuntimeError(f"LLM request failed: {e}") from e
        
        # Extract response text
        text = ""
        if hasattr(resp, "choices") and resp.choices:
            text = resp.choices[0].message.content.strip()
        
        # Calculate latency
        latency_ms = int((time.time() - start_time) * 1000)
        
        # Extract usage statistics
        raw_usage = {}
        if hasattr(resp, "usage"):
            raw_usage = resp.usage if isinstance(resp.usage, dict) else resp.usage.__dict__
        
        usage = {
            "tokens_in": int(raw_usage.get("prompt_tokens", 0) or 0),
            "tokens_out": int(raw_usage.get("completion_tokens", 0) or 0),
            "latency_ms": latency_ms,
            "usd_micros": self._estimate_cost_micros(raw_usage, m),
        }
        
        logger.info("litellm.finish", extra={
            "model": m,
            "resp_len": len(text),
            "tokens_in": usage["tokens_in"],
            "tokens_out": usage["tokens_out"],
            "latency_ms": latency_ms
        })
        
        return LLMReply(text=text, provider="litellm", model=m, usage=usage)
    
    def stream_chat(self, prompt: str, *, model: str | None = None) -> Iterable[str]:
        """Stream response tokens as they arrive.
        
        Args:
            prompt: Input prompt for the model
            model: Model name (uses default if not specified)
            
        Yields:
            Text chunks as they arrive from the model
        """
        m = model or self.model_default
        logger.info("litellm.stream_start", extra={"model": m, "api_base": self._api_base})
        
        try:
            # Prepare streaming request
            kwargs = {
                "model": m,
                "messages": [{"role": "user", "content": prompt}],
                "stream": True,
                "temperature": 0.0,
                "timeout": self.timeout,
            }
            
            if self._api_base:
                kwargs["api_base"] = self._api_base
            
            # Stream the response
            stream = litellm.completion(**kwargs)
            
            for chunk in stream:
                # Extract delta content
                if hasattr(chunk, "choices") and chunk.choices:
                    delta = chunk.choices[0].delta
                    
                    # Handle different delta formats
                    if hasattr(delta, "content"):
                        content = delta.content
                    elif isinstance(delta, dict) and "content" in delta:
                        content = delta["content"]
                    else:
                        content = None
                    
                    if content:
                        yield content
            
            logger.info("litellm.stream_finish", extra={"model": m})
            
        except Exception as e:
            logger.error("litellm.stream_error", extra={"model": m, "error": str(e)})
            # Use same error handling as chat()
            error_msg = str(e).lower()
            
            if "openai" in m and ("api" in error_msg or "key" in error_msg):
                raise RuntimeError(
                    f"OpenAI streaming error: Check OPENAI_API_KEY"
                ) from e
            
            if "ollama" in m and ("connection" in error_msg or "refused" in error_msg):
                raise RuntimeError(
                    f"Ollama streaming error: Check daemon at {self._api_base}"
                ) from e
            
            raise
    
    def _estimate_cost_micros(self, usage_data: dict, model: str) -> int:
        """Estimate cost in USD micros based on model and usage.
        
        Args:
            usage_data: Token usage statistics
            model: Model name for pricing lookup
            
        Returns:
            Estimated cost in USD micros (1/1000000 USD)
        """
        # Simplified pricing estimates (should be externalized)
        pricing = {
            "gpt-4o-mini": {"input": 0.15, "output": 0.60},  # per 1M tokens
            "gpt-4": {"input": 30.0, "output": 60.0},
            "gpt-3.5-turbo": {"input": 0.5, "output": 1.5},
        }
        
        # Extract base model name for pricing
        model_base = model.replace("openai/", "").replace("ollama/", "")
        model_pricing = pricing.get(model_base, {"input": 0, "output": 0})
        
        # Ollama is free
        if "ollama" in model:
            return 0
        
        prompt_tokens = usage_data.get("prompt_tokens", 0) or 0
        completion_tokens = usage_data.get("completion_tokens", 0) or 0
        
        # Calculate cost in USD, convert to micros
        input_cost = (prompt_tokens / 1_000_000) * model_pricing["input"]
        output_cost = (completion_tokens / 1_000_000) * model_pricing["output"]
        total_cost_usd = input_cost + output_cost
        
        return int(total_cost_usd * 1_000_000)