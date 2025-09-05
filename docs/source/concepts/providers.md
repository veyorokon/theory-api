(providers)=
# LLM Providers

Overview of Theory's LLM provider architecture, distinguishing between providers and models.

## Provider vs Model

Theory separates **providers** (infrastructure/API clients) from **models** (specific capabilities):

```
Provider:  How to connect (OpenAI API, Ollama daemon, etc.)
Model:     What to invoke (gpt-4o-mini, qwen2.5:0.5b, etc.)
```

This separation allows:
- **Flexibility**: Same provider can support multiple models
- **Consistency**: Unified interface across different backends
- **Testing**: Mock provider for CI, real providers for production

## Provider Types

### Mock Provider
- **Purpose**: Development, testing, CI/CD
- **Dependencies**: None
- **Models**: `mock` (deterministic responses)
- **Cost**: Free

### OpenAI Provider  
- **Purpose**: Cloud-based inference via OpenAI API
- **Dependencies**: `OPENAI_API_KEY` environment variable
- **Models**: `gpt-4o-mini`, `gpt-4`, `gpt-3.5-turbo`, etc.
- **Cost**: Metered per token (tracked in `usd_micros`)

### Ollama Provider
- **Purpose**: Local inference with open models
- **Dependencies**: Ollama daemon + pulled models
- **Models**: `qwen2.5:0.5b`, `llama3:8b`, `mistral:7b`, etc.
- **Cost**: Free (local compute)

## Usage Patterns

### CLI Selection
```bash
# Provider + default model
python manage.py hello_llm --provider mock
python manage.py hello_llm --provider openai  
python manage.py hello_llm --provider ollama

# Provider + specific model
python manage.py hello_llm --provider openai --model gpt-4
python manage.py hello_llm --provider ollama --model llama3:8b
```

### Programmatic Usage
```python
from apps.core.providers import get_llm_provider

# Factory pattern
llm = get_llm_provider('openai')
reply = llm.chat("Hello", model="gpt-4o-mini")

# Direct instantiation
from apps.core.providers.openai_api import OpenAIProvider
llm = OpenAIProvider(api_key="your-key")
reply = llm.chat("Hello", model="gpt-4")
```

## Configuration

### Environment Variables

| Provider | Variable | Default | Required |
|----------|----------|---------|----------|
| Mock | — | — | No |
| OpenAI | `OPENAI_API_KEY` | — | Yes |
| Ollama | `OLLAMA_HOST` | `http://localhost:11434` | No |

### Model Defaults

Each provider defines sensible defaults:

```python
default_models = {
    'mock': 'mock',
    'openai': 'gpt-4o-mini',  # Cost-effective
    'ollama': 'qwen2.5:0.5b'  # Lightweight
}
```

## Response Contract

All providers return standardized `LLMReply` objects:

```python
@dataclass
class LLMReply:
    text: str           # Generated response
    provider: str       # Provider name
    model: str          # Model used
    usage: dict         # Standardized metrics
```

### Usage Metrics

The `usage` dict includes consistent keys:

```python
{
    "tokens_in": 150,      # Input tokens
    "tokens_out": 87,      # Output tokens  
    "latency_ms": 1240,    # Response time
    "usd_micros": 23       # Cost in micro-USD (0 for local)
}
```

## Error Handling

### Provider Unavailable
```python
# Missing dependency or configuration
get_llm_provider('openai')  # No OPENAI_API_KEY
# → ValueError: Provider 'openai' is unavailable
```

### Model Not Found
```python  
# Ollama model not pulled
llm.chat("Hello", model="missing-model")
# → ValueError: Model 'missing-model' not found. Pull it with: ollama pull missing-model
```

### Network Issues
```python
# API unreachable
llm.chat("Hello")
# → requests.RequestException: OpenAI API unavailable
```

## Extension Points

### Adding New Providers

1. Implement the `LLMProvider` protocol:
   ```python
   class CustomProvider:
       def chat(self, prompt: str, *, model: str | None = None) -> LLMReply:
           # Your implementation
           pass
   ```

2. Register in factory:
   ```python
   # apps/core/providers/__init__.py
   def get_llm_provider(name: str):
       mapping = {
           'custom': CustomProvider(),
           # ...existing providers
       }
   ```

3. Add tests and documentation

### Streaming Support

Future extension via `LLMStreamProvider` protocol:

```python
class StreamingProvider(LLMProvider):
    def stream_chat(self, prompt: str, *, model: str | None = None) -> Iterable[str]:
        # Yield incremental response chunks
        pass
```

## Related Documentation

- [Hello LLM Use Case](../use-cases/hello-llm.md) - Provider usage examples
- [Registry and Adapters](registry-and-adapters.md) - General adapter patterns