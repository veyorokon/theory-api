"""
Mock LLM provider for development and testing.

Provides deterministic responses without external dependencies.
"""
import logging
from typing import Iterable

from apps.core.llm import LLMReply

logger = logging.getLogger(__name__)


class MockLLM:
    """Deterministic mock LLM for hello-world demos and testing.
    
    No external dependencies - perfect for development and CI environments.
    Supports both regular chat and streaming for testing.
    """
    
    def chat(self, prompt: str, *, model: str | None = None) -> LLMReply:
        """Generate a deterministic mock response.
        
        Args:
            prompt: Input prompt (echoed back in response)
            model: Model name (ignored for mock, defaults to "mock")
            
        Returns:
            LLMReply with formatted mock response
        """
        logger.info("mockllm.start", extra={"prompt_len": len(prompt)})
        
        text = f"Hello from MockLLM! You said: {prompt.strip()}"
        
        logger.info("mockllm.finish", extra={"resp_len": len(text)})
        
        return LLMReply(
            text=text,
            provider="mock",
            model=model or "mock",
            usage={
                "tokens_in": len(prompt.split()),
                "tokens_out": len(text.split()), 
                "latency_ms": 1,
                "usd_micros": 0
            }
        )
    
    def stream_chat(self, prompt: str, *, model: str | None = None) -> Iterable[str]:
        """Stream a deterministic mock response word by word.
        
        Args:
            prompt: Input prompt (echoed back in response)
            model: Model name (ignored for mock, defaults to "mock")
            
        Yields:
            Words from the response text, one at a time
        """
        logger.info("mockllm.stream_start", extra={"prompt_len": len(prompt)})
        
        # Generate the same response as chat()
        text = f"Hello from MockLLM! You said: {prompt.strip()}"
        words = text.split()
        
        # Stream words one at a time for realistic simulation
        for i, word in enumerate(words):
            if i > 0:
                yield " "  # Add space between words
            yield word
        
        logger.info("mockllm.stream_finish", extra={"resp_len": len(text)})