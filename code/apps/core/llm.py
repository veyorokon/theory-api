"""
LLM Provider interface and implementations for Theory processors.

Provides a unified interface for LLM interactions with extensible reply containers.
"""
import logging
from dataclasses import dataclass, field
from typing import Protocol, Iterable

logger = logging.getLogger(__name__)


@dataclass
class LLMReply:
    """LLM response container with standardized usage tracking.
    
    Extensible without breaking call sites. Usage dict includes standardized
    keys: tokens_in, tokens_out, latency_ms, usd_micros.
    """
    text: str
    provider: str
    model: str
    usage: dict = field(default_factory=lambda: {
        'tokens_in': 0,
        'tokens_out': 0, 
        'latency_ms': 0,
        'usd_micros': 0,
    })


class LLMProvider(Protocol):
    """Protocol for LLM provider implementations."""
    
    def chat(self, prompt: str, *, model: str | None = None) -> LLMReply:
        """Generate a response to the given prompt.
        
        Args:
            prompt: Input text prompt for the LLM
            model: Model name (provider-specific default if None)
            
        Returns:
            LLMReply containing the response text and metadata
        """
        ...


class LLMStreamProvider(LLMProvider, Protocol):
    """Protocol for streaming LLM providers (future extension)."""
    
    def stream_chat(self, prompt: str, *, model: str | None = None) -> Iterable[str]:
        """Generate streaming response to the given prompt.
        
        Args:
            prompt: Input text prompt for the LLM  
            model: Model name (provider-specific default if None)
            
        Yields:
            Incremental response text chunks
        """
        ...


# Re-export MockLLM for backward compatibility
try:
    from .providers.mock import MockLLM  # type: ignore
except ImportError:  # pragma: no cover
    # Fallback for cases where providers package not available
    class MockLLM:  # type: ignore
        """Fallback mock implementation."""
        
        def chat(self, prompt: str, *, model: str | None = None) -> LLMReply:
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