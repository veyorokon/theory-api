"""
LLM Provider interface and implementations for Theory processors.

Provides a unified interface for LLM interactions with extensible reply containers.
"""
import logging
from dataclasses import dataclass, field
from typing import Protocol

logger = logging.getLogger(__name__)


@dataclass
class LLMReply:
    """Minimal LLM response container.
    
    Extensible without breaking call sites. Future usage may track tokens, 
    latency_ms, model_name, etc.
    """
    text: str
    provider: str = "mock"
    usage: dict = field(default_factory=dict)


class LLMProvider(Protocol):
    """Protocol for LLM provider implementations."""
    
    def chat(self, prompt: str) -> LLMReply:
        """Generate a response to the given prompt.
        
        Args:
            prompt: Input text prompt for the LLM
            
        Returns:
            LLMReply containing the response text and metadata
        """
        ...


class MockLLM:
    """Deterministic mock LLM for hello-world demos and testing.
    
    No external dependencies - perfect for development and CI environments.
    """
    
    def chat(self, prompt: str) -> LLMReply:
        """Generate a deterministic mock response.
        
        Args:
            prompt: Input prompt (echoed back in response)
            
        Returns:
            LLMReply with formatted mock response
        """
        logger.info("mockllm.start", extra={"prompt_len": len(prompt)})
        
        text = f"Hello from MockLLM! You said: {prompt.strip()}"
        
        logger.info("mockllm.finish", extra={"resp_len": len(text)})
        
        return LLMReply(
            text=text,
            provider="mock",
            usage={"prompt_tokens": len(prompt.split()), "completion_tokens": len(text.split())}
        )