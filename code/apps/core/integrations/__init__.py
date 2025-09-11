from typing import Any

from .mock import MockLLM

try:
    from .litellm_provider import LiteLLMProvider
except Exception:  # Optional dependency may be missing
    LiteLLMProvider = None  # type: ignore


def get_llm_provider(name: str, *, model_default: str = 'openai/gpt-4o-mini', api_base: str | None = None) -> Any:
    """Get LLM provider instance by name with configuration.

    Args:
        name: Provider name (mock, litellm)
        model_default: Default model to use
        api_base: Optional API base URL (e.g., Ollama)

    Returns:
        Provider instance

    Raises:
        ValueError: Unknown provider or provider unavailable
    """
    available = ['mock', 'litellm']
    if name not in available:
        raise ValueError(
            f"Unknown LLM provider: {name}. Available: {', '.join(available)}"
        )

    if name == 'mock':
        return MockLLM()

    if name == 'litellm':
        if not LiteLLMProvider:
            raise ValueError("LiteLLMProvider is unavailable; missing optional dependency")
        return LiteLLMProvider(model_default=model_default, api_base=api_base)

