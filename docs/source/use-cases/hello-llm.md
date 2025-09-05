(hello-llm-mock)=
# Hello LLM (Mock)

A minimal LLM processor demonstration using Theory's provider interface. This example establishes patterns for future LLM integrations without requiring external API keys or network dependencies.

## Quick Start

Run the hello world demo without any setup:

```bash
cd theory_api/code && python manage.py hello_llm --prompt "Hello, Theory!"
```

**Expected Output:**
```
Hello from MockLLM! You said: Hello, Theory!
```

## JSON Output

For programmatic usage, enable JSON output:

```bash
cd theory_api/code && python manage.py hello_llm --prompt "Hello, Theory!" --json
```

**Expected JSON Structure:**
```json
{
  "text": "Hello from MockLLM! You said: Hello, Theory!",
  "provider": "mock",
  "usage": {
    "prompt_tokens": 2,
    "completion_tokens": 9
  }
}
```

## Implementation Details

### LLMReply Dataclass

The `LLMReply` container provides extensible response metadata:

```python
from apps.core.llm import LLMReply

reply = LLMReply(
    text="Response text",
    provider="mock",
    usage={"prompt_tokens": 5, "completion_tokens": 10}
)
```

### MockLLM Provider

The deterministic mock implementation:

```python
from apps.core.llm import MockLLM

llm = MockLLM()
reply = llm.chat("Your prompt here")
print(reply.text)  # "Hello from MockLLM! You said: Your prompt here"
```

### Provider Protocol

Future LLM providers implement the `LLMProvider` protocol:

```python
from apps.core.llm import LLMProvider, LLMReply

class CustomLLM:
    def chat(self, prompt: str) -> LLMReply:
        # Custom implementation
        return LLMReply(text="...", provider="custom")
```

## Command Options

| Option | Description | Default |
|--------|-------------|---------|
| `--prompt` | Input prompt text | `"hello world"` |
| `--json` | Output JSON instead of plain text | `False` |

## Logging

The MockLLM provider emits structured logs for observability:

```python
import logging
logging.basicConfig(level=logging.INFO)

llm = MockLLM()
llm.chat("test")
# INFO:apps.core.llm:mockllm.start {"prompt_len": 4}
# INFO:apps.core.llm:mockllm.finish {"resp_len": 35}
```

## Testing

Run the comprehensive test suite:

```bash
cd theory_api/code && python -m pytest apps/core/tests/test_hello_llm.py -v
```

Tests cover:
- LLMReply dataclass functionality
- MockLLM provider behavior
- Management command execution
- JSON output format
- Structured logging assertions

## Future Extensions

This mock establishes patterns for real LLM providers:

- **OpenAI GPT**: Replace MockLLM with OpenAI API client
- **Anthropic Claude**: Add Claude-specific provider implementation
- **Local Models**: Support for Ollama, vLLM, or other local inference
- **Usage tracking**: Extend `usage` dict with tokens, latency, cost
- **Streaming**: Add streaming response support to protocol

## Related Documentation

- [Processors and Adapters](../concepts/registry-and-adapters.md) - Provider pattern concepts
- [Core App](../apps/core.md) - Management commands and utilities