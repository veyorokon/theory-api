(hello-llm-mock)=
# Hello LLM

A flexible LLM processor demonstration using Theory's provider interface. Supports multiple providers through LiteLLM substrate with streaming capabilities. Unified CLI and extensible patterns for future integrations.

## Quick Start

### Mock Provider (No Setup Required)

Run the hello world demo without any setup:

```bash
cd theory_api/code && python manage.py hello_llm --prompt "Hello, Theory!"
```

**Expected Output:**
```
Hello from MockLLM! You said: Hello, Theory!
```

### LiteLLM Provider (OpenAI)

With OpenAI API key via LiteLLM:

```bash
export OPENAI_API_KEY="your-key-here"
cd theory_api/code && python manage.py hello_llm --provider litellm --model openai/gpt-4o-mini --prompt "Hello, Theory!"
```

### LiteLLM Provider (Ollama)

With Ollama daemon running locally:

```bash
# Start Ollama daemon and pull model
ollama serve
ollama pull qwen2.5:0.5b

cd theory_api/code && python manage.py hello_llm --provider litellm --model ollama/qwen2.5:0.5b --api-base http://127.0.0.1:11434 --prompt "Hello, Theory!"
```

## Selecting a Provider & Model

```bash
# Mock provider (default)
python manage.py hello_llm --provider mock --prompt "Hi"

# OpenAI via LiteLLM
python manage.py hello_llm --provider litellm --model openai/gpt-4o-mini --prompt "Hi"

# Ollama via LiteLLM
python manage.py hello_llm --provider litellm --model ollama/qwen2.5:0.5b --api-base http://127.0.0.1:11434 --prompt "Hi"
```

| Provider | Default Model  | Environment Variables | When to Use |
|----------|----------------|----------------------|-------------|
| `mock`   | `mock`         | —                   | CI, docs, no network/keys |
| `litellm` | `openai/gpt-4o-mini`  | `OPENAI_API_KEY` (OpenAI), `LLM_API_BASE` (Ollama) | Unified interface for 100+ LLM providers |

## JSON Output

For programmatic usage, enable JSON output:

```bash
cd theory_api/code && python manage.py hello_llm --provider litellm --model openai/gpt-4o-mini --prompt "Hello, Theory!" --json
```

**Expected JSON Structure:**
```json
{
  "text": "Hello! I'm an AI assistant. How can I help you today?",
  "provider": "litellm",
  "model": "openai/gpt-4o-mini",
  "usage": {
    "tokens_in": 3,
    "tokens_out": 12,
    "latency_ms": 1245,
    "usd_micros": 18
  }
}
```

## Implementation Details

### LLMReply Dataclass

The `LLMReply` container provides standardized response metadata:

```python
from apps.core.llm import LLMReply

reply = LLMReply(
    text="Response text",
    provider="openai",
    model="gpt-4o-mini",
    usage={
        "tokens_in": 5,
        "tokens_out": 10,
        "latency_ms": 850,
        "usd_micros": 25
    }
)
```

### Provider Selection

Use the factory function for consistent provider access:

```python
from apps.core.providers import get_llm_provider

# Get any provider
llm = get_llm_provider('mock')  # or 'litellm' for unified access
reply = llm.chat("Your prompt here", model="custom-model")
print(reply.text)

# LiteLLM with specific configuration
llm = get_llm_provider('litellm', model_default='openai/gpt-4o-mini', api_base='http://127.0.0.1:11434')
reply = llm.chat("Your prompt here")
print(reply.text)
```

### MockLLM Provider

The deterministic mock implementation:

```python
from apps.core.providers.mock import MockLLM

llm = MockLLM()
reply = llm.chat("Your prompt here", model="mock")
print(reply.text)  # "Hello from MockLLM! You said: Your prompt here"
```

### Provider Protocol

All LLM providers implement the unified `LLMProvider` protocol:

```python
from typing import Iterable
from apps.core.llm import LLMProvider, LLMReply

class CustomLLM:
    def chat(self, prompt: str, *, model: str | None = None) -> LLMReply:
        # Custom implementation
        return LLMReply(
            text="Custom response", 
            provider="custom",
            model=model or "default-model"
        )
    
    def stream_chat(self, prompt: str, *, model: str | None = None) -> Iterable[str]:
        # Streaming implementation
        yield "Custom "
        yield "streaming "
        yield "response"
```

## Command Options

## Streaming Support

All providers support real-time token streaming:

```bash
# Stream mock responses
cd theory_api/code && python manage.py hello_llm --provider mock --stream --prompt "Hello, Theory!"

# Stream OpenAI responses via LiteLLM
cd theory_api/code && python manage.py hello_llm --provider litellm --model openai/gpt-4o-mini --stream --prompt "Hello, Theory!"

# Stream Ollama responses via LiteLLM  
cd theory_api/code && python manage.py hello_llm --provider litellm --model ollama/qwen2.5:0.5b --api-base http://127.0.0.1:11434 --stream --prompt "Hello, Theory!"
```

**Streaming Behavior:**
- Tokens are output directly to stdout as they arrive
- No JSON output in stream mode
- Real-time visualization of model generation
- Supports all LiteLLM-compatible providers

### Programmatic Streaming

```python
from apps.core.providers import get_llm_provider

llm = get_llm_provider('litellm', model_default='openai/gpt-4o-mini')

for chunk in llm.stream_chat("Tell me about Theory"):
    print(chunk, end='', flush=True)
print()  # Final newline
```

## Command Options

| Option | Description | Default |
| `--prompt` | Input prompt text | `"hello world"` |
| `--json` | Output JSON instead of plain text | `False` |
| `--provider` | LLM provider (mock, litellm) | `mock` |
| `--model` | Model name (uses provider default if not specified) | Provider-specific |
| `--api-base` | API base URL (for Ollama or custom endpoints) | None |
| `--stream` | Stream tokens to stdout in real-time | `False` |

## Environment Variables

### Django Settings Integration

```bash
# LLM provider defaults (used by Django settings)
export LLM_PROVIDER_DEFAULT="litellm"         # Default provider
export LLM_MODEL_DEFAULT="openai/gpt-4o-mini" # Default model
export LLM_API_BASE="http://127.0.0.1:11434"  # Default API base (for Ollama)
```

### Provider-Specific Variables

```bash
# OpenAI (via LiteLLM)
export OPENAI_API_KEY="your-openai-key"  # Required for OpenAI models

# Ollama (via LiteLLM)
# No environment variables required - uses --api-base or LLM_API_BASE

# Ensure Ollama is running and model is pulled
ollama serve
ollama pull qwen2.5:0.5b
```

## Logging

All providers emit structured logs for observability:

```python
import logging
logging.basicConfig(level=logging.INFO)

from apps.core.providers import get_llm_provider

llm = get_llm_provider('litellm')
llm.chat("test", model="openai/gpt-4o-mini")
# INFO:apps.core.providers.litellm_provider:litellm.start {"model": "openai/gpt-4o-mini", "api_base": null}
# INFO:apps.core.providers.litellm_provider:litellm.finish {"model": "openai/gpt-4o-mini", "resp_len": 42, "tokens_in": 1, "tokens_out": 8, "latency_ms": 1200}
```

## Testing

Run the comprehensive test suite:

```bash
cd theory_api/code && python manage.py test apps.core.tests -v 2
```

Tests cover:
- All provider implementations (mock, LiteLLM unified)
- HTTP mocking for external providers (no network calls in CI)
- Provider factory and error handling
- Management command with all flags including streaming
- JSON output format and structure
- Structured logging assertions
- Environment variable and Django settings integration
- Streaming token generation and error handling

## Error Handling

The system provides clear error messages for common issues:

```bash
# Missing OpenAI API key
$ python manage.py hello_llm --provider litellm --model openai/gpt-4o-mini
Error: OpenAI API error: OPENAI_API_KEY missing or invalid. Set OPENAI_API_KEY environment variable and retry.

# Ollama daemon not running
$ python manage.py hello_llm --provider litellm --model ollama/qwen2.5:0.5b --api-base http://127.0.0.1:11434
Error: Ollama daemon unreachable at http://127.0.0.1:11434. Ensure 'ollama serve' is running and accessible.

# Model not pulled in Ollama
$ python manage.py hello_llm --provider litellm --model ollama/unknown-model --api-base http://127.0.0.1:11434
Error: Ollama model 'unknown-model' not found. Pull it with: ollama pull unknown-model
```

## Future Extensions

The LiteLLM-based system supports easy extension:

- **100+ Models**: LiteLLM supports Anthropic Claude, Azure OpenAI, Google Gemini, etc.
- **Custom Endpoints**: Any OpenAI-compatible API via `--api-base`
- **Advanced Streaming**: Server-sent events, WebSocket streaming
- **Cost Tracking**: Enhanced usage metrics and budget enforcement with LiteLLM's cost tracking
- **Model Management**: Automatic model discovery and validation
- **Multi-modal**: Image and function calling through LiteLLM

## Related Documentation

- [LLM Providers](../concepts/providers.md) - Provider vs model concepts
- [Processors and Adapters](../concepts/registry-and-adapters.md) - Provider pattern concepts
- [Core App](../apps/core.md) - Management commands and utilities