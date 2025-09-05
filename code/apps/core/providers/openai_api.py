"""
OpenAI API provider for LLM interactions.

Requires OPENAI_API_KEY environment variable.
"""
import logging
import os
import time
from typing import Any, Dict

import requests

from apps.core.llm import LLMReply

logger = logging.getLogger(__name__)


class OpenAIProvider:
    """OpenAI API client for GPT models."""
    
    def __init__(self, api_key: str | None = None, base_url: str = "https://api.openai.com/v1"):
        """Initialize OpenAI provider.
        
        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
            base_url: OpenAI API base URL
            
        Raises:
            ValueError: Missing API key
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OpenAI API key required. Set OPENAI_API_KEY environment variable "
                "or pass api_key parameter."
            )
        
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        })
    
    def chat(self, prompt: str, *, model: str | None = None) -> LLMReply:
        """Generate response using OpenAI Chat Completions API.
        
        Args:
            prompt: Input prompt for the model
            model: Model name (defaults to gpt-4o-mini)
            
        Returns:
            LLMReply with response text and usage metadata
            
        Raises:
            requests.RequestException: API request failed
        """
        model = model or "gpt-4o-mini"
        
        logger.info("openai.start", extra={"model": model, "prompt_len": len(prompt)})
        start_time = time.time()
        
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1000,
            "temperature": 0.7
        }
        
        try:
            response = self.session.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            latency_ms = int((time.time() - start_time) * 1000)
            
            # Extract response text
            text = data["choices"][0]["message"]["content"].strip()
            
            # Extract usage statistics  
            usage_data = data.get("usage", {})
            usage = {
                "tokens_in": usage_data.get("prompt_tokens", 0),
                "tokens_out": usage_data.get("completion_tokens", 0),
                "latency_ms": latency_ms,
                "usd_micros": self._estimate_cost_micros(usage_data, model)
            }
            
            logger.info("openai.finish", extra={
                "model": model,
                "resp_len": len(text),
                "tokens_in": usage["tokens_in"],
                "tokens_out": usage["tokens_out"],
                "latency_ms": latency_ms
            })
            
            return LLMReply(
                text=text,
                provider="openai", 
                model=model,
                usage=usage
            )
            
        except requests.RequestException as e:
            logger.error("openai.error", extra={"error": str(e), "model": model})
            raise
    
    def _estimate_cost_micros(self, usage_data: Dict[str, Any], model: str) -> int:
        """Estimate cost in USD micros (1/1000000 USD).
        
        Args:
            usage_data: Usage statistics from OpenAI response
            model: Model name for pricing lookup
            
        Returns:
            Estimated cost in USD micros
        """
        # Rough pricing estimates (as of 2024) - should be externalized
        pricing = {
            "gpt-4o-mini": {"input": 0.15, "output": 0.60},  # per 1M tokens
            "gpt-4": {"input": 30.0, "output": 60.0},
            "gpt-3.5-turbo": {"input": 0.5, "output": 1.5},
        }
        
        model_pricing = pricing.get(model, pricing["gpt-4o-mini"])
        
        prompt_tokens = usage_data.get("prompt_tokens", 0)
        completion_tokens = usage_data.get("completion_tokens", 0)
        
        # Calculate cost in USD, convert to micros
        input_cost = (prompt_tokens / 1_000_000) * model_pricing["input"]
        output_cost = (completion_tokens / 1_000_000) * model_pricing["output"]
        total_cost_usd = input_cost + output_cost
        
        return int(total_cost_usd * 1_000_000)