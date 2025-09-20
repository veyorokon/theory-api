(providers)=
# Integrations (LLM Providers)

Overview of Theory's server-side integrations (LLM providers) and how they differ from runtime processors.

## Provider vs Model

Providers implement transport (OpenAI, Replicate, Ollama, etc.); models represent capabilities (`gpt-4o-mini`, `qwen2.5`, etc.). Inputs include a `mode` flag:

- `mode="mock"` → deterministic mock response
- `mode="real"` → uses the real provider (requires secrets)

## Provider Types

### Mock Provider
- Purpose: development/testing via `mode=mock`
- Dependencies: none
- Model: `mock`
- Cost: free, deterministic output

### LiteLLM Provider
- Purpose: unified bridge to OpenAI, Anthropic, Ollama
- Dependencies: provider-specific env vars (e.g., `OPENAI_API_KEY`)
- Models: vendor-qualified strings (`openai/gpt-4o-mini`, `ollama/qwen2.5`)
- Cost: provider-specific billing

## Usage Patterns

### CLI Selection

```bash
# Mock mode (hermetic)
python manage.py run_processor --ref llm/litellm@1 --adapter local --mode mock

# Real mode (Docker)
python manage.py run_processor --ref llm/litellm@1 --adapter local --mode real

# Modal real run
python manage.py run_processor --ref llm/litellm@1 --adapter modal --mode real

# Attachments (still mock mode)
python manage.py run_processor --ref llm/litellm@1 --adapter local --mode mock --attach image=photo.jpg
```

### Programmatic Usage

```python
from libs.runtime_common.mode import resolve_mode, is_mock
from apps.core.integrations import get_llm_provider

runner = get_llm_provider("litellm")
mode = resolve_mode(inputs)
if is_mock(mode):
    # generate deterministic output
else:
    # call real provider (requires OPENAI_API_KEY)
```

## Configuration

### Environment Variables

| Provider | Key | Required in real mode |
|----------|-----|-----------------------|
| Mock | — | No |
| LiteLLM (OpenAI) | `OPENAI_API_KEY` | Yes |
| LiteLLM (Ollama) | `LLM_API_BASE` | Optional |

### Defaults

```python
default_models = {
    "mock": "mock",
    "litellm": "openai/gpt-4o-mini",
}
```

## Error Handling

Mock mode should never raise unless the schema is invalid. Real mode raises `RuntimeError` if required secrets are missing or provider call fails (wrap with `ERR_MISSING_SECRET`, etc.).

## Extension Points

Implement new providers by following the `LLMProvider` protocol and honouring `resolve_mode` so both mock and real paths stay in sync.
