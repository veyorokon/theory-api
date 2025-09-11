"""Mock LLM provider for development and testing."""
import logging
from apps.core.llm import LLMReply

logger = logging.getLogger(__name__)


class MockLLM:
    """Deterministic mock LLM for hello-world demos and testing.
    
    Provides both chat and streaming chat APIs for compatibility.
    """

    def chat(self, prompt: str, *, model: str | None = None) -> LLMReply:
        """Generate a deterministic mock response.
        
        Args:
            prompt: Input prompt for the model
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
            usage={"tokens_in": 1, "tokens_out": len(text.split()), "latency_ms": 0},
        )

    def stream_chat(self, prompt: str, *, model: str | None = None):
        """Stream a deterministic mock response word by word.
        
        Args:
            prompt: Input prompt for the model
            model: Model name (ignored for mock, defaults to "mock")
        Yields:
            Text chunks one by one
        """
        logger.info("mockllm.stream_start", extra={"prompt_len": len(prompt)})
        text = f"Hello from MockLLM! You said: {prompt.strip()}"
        for word in text.split():
            yield word
        logger.info("mockllm.stream_finish", extra={"resp_len": len(text)})

