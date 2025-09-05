"""
Ollama local LLM provider.

Connects to local Ollama daemon for model inference.
"""
import logging
import os
import time
from typing import Any, Dict

import requests

from apps.core.llm import LLMReply

logger = logging.getLogger(__name__)


class OllamaProvider:
    """Ollama local LLM client."""
    
    def __init__(self, host: str | None = None):
        """Initialize Ollama provider.
        
        Args:
            host: Ollama daemon host (defaults to OLLAMA_HOST env var or localhost:11434)
        """
        self.host = host or os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
    
    def chat(self, prompt: str, *, model: str | None = None) -> LLMReply:
        """Generate response using Ollama generate API.
        
        Args:
            prompt: Input prompt for the model
            model: Model name (defaults to qwen2.5:0.5b)
            
        Returns:
            LLMReply with response text and usage metadata
            
        Raises:
            requests.RequestException: Ollama daemon unavailable
            ValueError: Model not found or not pulled
        """
        model = model or "qwen2.5:0.5b"
        
        logger.info("ollama.start", extra={"model": model, "prompt_len": len(prompt)})
        start_time = time.time()
        
        # Check if daemon is available
        try:
            self.session.get(f"{self.host}/api/version", timeout=5)
        except requests.RequestException as e:
            raise requests.RequestException(
                f"Ollama daemon unavailable at {self.host}. "
                f"Install with: curl -fsSL https://ollama.com/install.sh | sh && ollama serve"
            ) from e
        
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "num_predict": 512
            }
        }
        
        try:
            response = self.session.post(
                f"{self.host}/api/generate",
                json=payload,
                timeout=120  # Local models can be slower
            )
            response.raise_for_status()
            
            data = response.json()
            latency_ms = int((time.time() - start_time) * 1000)
            
            # Check for model errors
            if "error" in data:
                if "model not found" in data["error"].lower():
                    raise ValueError(
                        f"Model '{model}' not found. Pull it with: ollama pull {model}"
                    )
                else:
                    raise ValueError(f"Ollama error: {data['error']}")
            
            text = data.get("response", "").strip()
            
            # Estimate token counts (Ollama doesn't always provide these)
            prompt_tokens = data.get("prompt_eval_count", len(prompt.split()))
            completion_tokens = data.get("eval_count", len(text.split()))
            
            usage = {
                "tokens_in": prompt_tokens,
                "tokens_out": completion_tokens,
                "latency_ms": latency_ms,
                "usd_micros": 0  # Local inference is free
            }
            
            logger.info("ollama.finish", extra={
                "model": model,
                "resp_len": len(text),
                "tokens_in": usage["tokens_in"],
                "tokens_out": usage["tokens_out"], 
                "latency_ms": latency_ms
            })
            
            return LLMReply(
                text=text,
                provider="ollama",
                model=model,
                usage=usage
            )
            
        except requests.RequestException as e:
            logger.error("ollama.error", extra={"error": str(e), "model": model})
            if response.status_code == 404:
                raise ValueError(
                    f"Model '{model}' not found. Available models: "
                    f"{self._get_available_models()}"
                )
            raise
    
    def _get_available_models(self) -> str:
        """Get list of available models from Ollama.
        
        Returns:
            Comma-separated model names or error message
        """
        try:
            response = self.session.get(f"{self.host}/api/tags", timeout=5)
            response.raise_for_status()
            
            models = response.json().get("models", [])
            if models:
                return ", ".join(model["name"] for model in models)
            else:
                return "none (pull a model with: ollama pull qwen2.5:0.5b)"
                
        except requests.RequestException:
            return "unable to list (daemon may be down)"