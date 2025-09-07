"""
LLM Provider factory and imports.

Centralizes provider discovery and instantiation with graceful fallbacks.
"""
from typing import Any

from .mock import MockLLM

# Optional providers - graceful import fallback
try:
    from .litellm_provider import LiteLLMProvider
except ImportError:  # pragma: no cover
    LiteLLMProvider = None  # type: ignore



def get_llm_provider(name: str, *, model_default: str = 'openai/gpt-4o-mini', api_base: str | None = None) -> Any:
    """Get LLM provider instance by name with configuration.
    
    Args:
        name: Provider name (mock, litellm)
        model_default: Default model to use if not specified in chat()
        api_base: Optional API base URL (for Ollama or custom endpoints)
        
    Returns:
        Provider instance ready for chat() and stream_chat() calls
        
    Raises:
        ValueError: Unknown provider or provider unavailable
    """
    # Use lazy construction to pass parameters
    if name == 'mock':
        return MockLLM()
    
    if name == 'litellm':
        if not LiteLLMProvider:
            raise ValueError(
                "LiteLLM unavailable - install 'litellm' dependency"
            )
        return LiteLLMProvider(model_default=model_default, api_base=api_base)
    
    # Unknown provider
    available = ['mock', 'litellm']
    raise ValueError(
        f"Unknown LLM provider: {name}. Available: {', '.join(available)}"
    )