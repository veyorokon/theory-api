"""
LLM Provider factory and imports.

Centralizes provider discovery and instantiation with graceful fallbacks.
"""
from typing import Dict, Any

from .mock import MockLLM

# Optional providers - graceful import fallback
try:
    from .openai_api import OpenAIProvider
except ImportError:  # pragma: no cover
    OpenAIProvider = None  # type: ignore

try:
    from .ollama import OllamaProvider  
except ImportError:  # pragma: no cover
    OllamaProvider = None  # type: ignore


def get_llm_provider(name: str) -> Any:
    """Get LLM provider instance by name.
    
    Args:
        name: Provider name (mock, openai, ollama)
        
    Returns:
        Provider instance ready for chat() calls
        
    Raises:
        ValueError: Unknown provider or provider unavailable
    """
    mapping: Dict[str, Any] = {
        'mock': MockLLM(),
        'openai': OpenAIProvider() if OpenAIProvider else None,
        'ollama': OllamaProvider() if OllamaProvider else None,
    }
    
    try:
        provider = mapping[name]
        if provider is None:
            raise ValueError(
                f"Provider '{name}' is unavailable (missing dependency or not configured)"
            )
        return provider
    except KeyError:
        available = [k for k, v in mapping.items() if v is not None]
        raise ValueError(
            f"Unknown LLM provider: {name}. Available: {', '.join(available)}"
        )