# Configuration Reference

## Global Configuration

| Name            | Where           | Purpose                                                  |
|-----------------|-----------------|----------------------------------------------------------|
| `MODAL_ENABLED` | Django settings | Enable Modal adapter.                                    |
| `MODAL_ENV`     | env/settings    | Logical env name (`dev`, `staging`, `main`); feeds `--env`. |
| `PROCESSOR_REF` | env             | Set by workflows when deploying a specific processor.    |

App names are now derived automatically:
- CI/CD (`modal_app.py`): `modal_app_name_from_ref(ref)` → `llm-litellm-v1`
- Manual commands: `_modalctl.resolve_app_name(env, ref)` → `user-branch-llm-litellm-v1`
No `MODAL_APP_NAME` override is required.

## Secrets Standard

**Secret names equal the environment variable names** used by processors.

| Secret name        | Used for       | Notes                                                                                         |
|--------------------|----------------|-----------------------------------------------------------------------------------------------|
| `OPENAI_API_KEY`   | LLM processors | Required for `mode=real` executions that call OpenAI through LiteLLM.                         |
| `LITELLM_API_BASE` | LLM processors | Optional; custom LiteLLM endpoint.                                                            |
| `REGISTRY_AUTH`    | GHCR pulls     | Contains keys `REGISTRY_USERNAME` and `REGISTRY_PASSWORD` (GitHub PAT with `read:packages`). |

The `env_fingerprint` includes only **secret names**, keeping values secure.
