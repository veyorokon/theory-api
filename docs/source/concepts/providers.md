(providers)=
# Integrations (LLM Providers)

Overview of Theory's server-side integrations (LLM providers) and how they differ from runtime processors.

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

### LiteLLM Provider
- **Purpose**: Unified substrate that talks to many backends (OpenAI, Ollama, Anthropic, etc.)
- **Dependencies**: Provider-specific envs (e.g., `OPENAI_API_KEY` for OpenAI) or `--api-base` for local gateways
- **Models**: Use vendor‑qualified strings (e.g., `openai/gpt-4o-mini`, `ollama/qwen2.5:0.5b`)
- **Cost**: Metered for cloud; local compute for Ollama

## Usage Patterns

### CLI Selection
```bash
# Smoke mode (hermetic testing, no external services)
python manage.py run_processor --ref llm/litellm@1 --adapter local --mode smoke

# Modal adapter for cloud execution
python manage.py run_processor --ref llm/litellm@1 --adapter modal

# With attachments (smoke mode still works locally)
python manage.py run_processor --ref llm/litellm@1 --adapter local --mode smoke --attach image=photo.jpg
```

### Programmatic Usage (Server-side)
```python
from apps.core.integrations import get_llm_provider

# Factory pattern
llm = get_llm_provider('litellm', model_default='openai/gpt-4o-mini')
reply = llm.chat("Hello")
```

## Configuration

### Environment Variables

| Provider | Variable | Default | Required |
|----------|----------|---------|----------|
| Mock | — | — | No |
| LiteLLM (OpenAI) | `OPENAI_API_KEY` | — | Yes |
| LiteLLM (Ollama) | `LLM_API_BASE` | `http://localhost:11434` | No |

### Model Defaults

Sensible defaults:

```python
default_models = {
    'mock': 'mock',
    'litellm': 'openai/gpt-4o-mini',  # cost-effective default
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
# Missing dependency or configuration (OpenAI)
llm = get_llm_provider('litellm', model_default='openai/gpt-4o-mini')
llm.chat("hi")  # No OPENAI_API_KEY
# → RuntimeError: OPENAI_API_KEY missing or OpenAI unreachable.
```

### Model Not Found
```python
# Ollama model not pulled
llm = get_llm_provider('litellm', model_default='ollama/qwen2.5:0.5b', api_base='http://127.0.0.1:11434')
llm.chat("Hello")
# → RuntimeError: Ollama unreachable. Ensure ollama serve is running and model is pulled (e.g., 'ollama pull qwen3:0.6b').
```

### Network Issues
```python
# API unreachable
llm = get_llm_provider('litellm', model_default='openai/gpt-4o-mini')
llm.chat("Hello")
# → RuntimeError: OPENAI_API_KEY missing or OpenAI unreachable.
```

## Extension Points

### Adding New Integrations

1. Implement the `LLMProvider` protocol:
   ```python
   class CustomProvider:
       def chat(self, prompt: str, *, model: str | None = None) -> LLMReply:
           # Your implementation
           pass
   ```

2. Register in factory:
   ```python
   # apps/core/integrations/__init__.py
   def get_llm_provider(name: str):
       mapping = {
           'custom': CustomProvider(),
           # ...existing providers
       }
   ```

3. Add tests and documentation

### Streaming Support

Providers may implement streaming via `stream_chat(prompt, *, model=None) -> Iterable[str]`.
LiteLLM supports streaming; MockLLM yields deterministic chunks for demos and tests.

## Related Documentation

- [Run Processor Use Case](../use-cases/run-processor.md) - Processor execution examples
- [Registry and Adapters](registry-and-adapters.md) - General adapter patterns
