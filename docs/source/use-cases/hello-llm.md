(hello-llm-mock)=
# Hello LLM

A flexible LLM processor demonstration using Theory's provider interface. Supports multiple providers (mock, OpenAI, Ollama) with unified CLI and extensible patterns for future integrations.

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

### OpenAI Provider

With OpenAI API key:

```bash
export OPENAI_API_KEY="your-key-here"
cd theory_api/code && python manage.py hello_llm --provider openai --prompt "Hello, Theory!"
```

### Ollama Provider

With Ollama daemon running locally:

```bash
# Start Ollama daemon and pull model
ollama serve
ollama pull qwen2.5:0.5b

cd theory_api/code && python manage.py hello_llm --provider ollama --prompt "Hello, Theory!"
```

## Selecting a Provider & Model

```bash
# Mock provider (default)
python manage.py hello_llm --provider mock --prompt "Hi"

# OpenAI with specific model
python manage.py hello_llm --provider openai --model gpt-4o-mini --prompt "Hi"

# Ollama with local model
python manage.py hello_llm --provider ollama --model qwen2.5:0.5b --prompt "Hi"
```

| Provider | Default Model  | Environment Variable | When to Use |
|----------|----------------|----------------------|-------------|
| `mock`   | `mock`         | —                   | CI, docs, no network/keys |
| `openai` | `gpt-4o-mini`  | `OPENAI_API_KEY`    | API-based demo; HTTP mocked in tests |
| `ollama` | `qwen2.5:0.5b` | `OLLAMA_HOST`       | Local daemon with pulled model |

## JSON Output

For programmatic usage, enable JSON output:

```bash
cd theory_api/code && python manage.py hello_llm --provider openai --model gpt-4o-mini --prompt "Hello, Theory!" --json
```

**Expected JSON Structure:**
```json
{
  "text": "Hello! I'm Claude, an AI assistant created by Anthropic...",
  "provider": "openai",
  "model": "gpt-4o-mini",
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
llm = get_llm_provider('mock')  # or 'openai', 'ollama'
reply = llm.chat("Your prompt here", model="custom-model")
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
from apps.core.llm import LLMProvider, LLMReply

class CustomLLM:
    def chat(self, prompt: str, *, model: str | None = None) -> LLMReply:
        # Custom implementation
        return LLMReply(
            text="Custom response", 
            provider="custom",
            model=model or "default-model"
        )
```

## Command Options

| Option | Description | Default |
|--------|-------------|---------|
| `--prompt` | Input prompt text | `"hello world"` |
| `--json` | Output JSON instead of plain text | `False` |
| `--provider` | LLM provider (mock, openai, ollama) | `mock` |
| `--model` | Model name (uses provider default if not specified) | Provider-specific |

## Environment Variables

### OpenAI Provider

```bash
export OPENAI_API_KEY="your-openai-key"  # Required for OpenAI provider
```

### Ollama Provider

```bash
export OLLAMA_HOST="http://localhost:11434"  # Optional, defaults to localhost:11434

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

llm = get_llm_provider('openai')
llm.chat("test", model="gpt-4o-mini")
# INFO:apps.core.providers.openai_api:openai.start {"model": "gpt-4o-mini", "prompt_len": 4}
# INFO:apps.core.providers.openai_api:openai.finish {"model": "gpt-4o-mini", "resp_len": 42, "tokens_in": 1, "tokens_out": 8, "latency_ms": 1200}
```

## Testing

Run the comprehensive test suite:

```bash
cd theory_api/code && python manage.py test apps.core.tests -v 2
```

Tests cover:
- All provider implementations (mock, OpenAI, Ollama)
- HTTP mocking for external providers (no network calls in CI)
- Provider factory and error handling
- Management command with all flags
- JSON output format and structure
- Structured logging assertions
- Environment variable handling

## Error Handling

The system provides clear error messages for common issues:

```bash
# Missing OpenAI API key
$ python manage.py hello_llm --provider openai
Error: Provider 'openai' is unavailable (missing dependency or not configured)

# Ollama daemon not running
$ python manage.py hello_llm --provider ollama
Error: Ollama daemon unavailable at http://localhost:11434. Install with: curl -fsSL https://ollama.com/install.sh | sh && ollama serve

# Model not pulled in Ollama
$ python manage.py hello_llm --provider ollama --model unknown-model
Error: Model 'unknown-model' not found. Pull it with: ollama pull unknown-model
```

## Future Extensions

The provider system supports easy extension:

- **Anthropic Claude**: Add `apps/core/providers/anthropic.py`
- **Azure OpenAI**: Extend OpenAI provider with Azure endpoints
- **Local Models**: Additional providers for vLLM, Hugging Face, etc.
- **Streaming**: Implement `LLMStreamProvider` protocol
- **Cost Tracking**: Enhanced usage metrics and budget enforcement
- **Model Management**: Automatic model discovery and validation

## Related Documentation

- [LLM Providers](../concepts/providers.md) - Provider vs model concepts
- [Processors and Adapters](../concepts/registry-and-adapters.md) - Provider pattern concepts
- [Core App](../apps/core.md) - Management commands and utilities