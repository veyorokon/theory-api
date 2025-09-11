# Configuration Reference

## Global Configuration

Configuration values that apply across all environments.

| Name               | Where           | Purpose                                                                |
| ------------------ | --------------- | ---------------------------------------------------------------------- |
| `MODAL_ENABLED`    | Django settings | Enable Modal adapter.                                                  |
| `MODAL_ENV`        | env/settings    | Logical env name: `dev`, `staging`, `main`. Selects Modal environment. |
| `MODAL_APP_NAME`   | env             | Modal app name (default: `theory-rt`). Selected environment via CLI.   |
| `PRESENT_ENV_KEYS` | derived         | Recorded in `env_fingerprint` (sorted names only; never values).       |

## Secrets Standard

**The authoritative secrets policy for Theory API.**

### Core Principle

**Secret names = environment variable names** used by the tool/processor (e.g., `OPENAI_API_KEY`, `LITELLM_API_BASE`).

### Rules

- **Naming:** Secret names are **identical across all environments** (dev/staging/main)
- **Values:** Only secret values differ per environment
- **Consistency:** Code and tests assume the same names everywhere
- **Mounting:** Modal runtime secrets are mounted by name (1 secret per environment variable)

### Registry Authentication (Special Case)

**Registry auth:** Single secret named **`REGISTRY_AUTH`** containing keys:
- `REGISTRY_USERNAME` - GitHub username or organization  
- `REGISTRY_PASSWORD` - GitHub Personal Access Token with `read:packages` scope

This special case exists because Modal's `Image.from_registry()` expects a single secret with both username and password keys.

### Required Secrets

| Secret name        | Used for       | Notes                                                                                         |
| ------------------ | -------------- | --------------------------------------------------------------------------------------------- |
| `OPENAI_API_KEY`   | LLM processors | Required for OpenAI models.                                                                   |
| `LITELLM_API_BASE` | LLM processors | Optional. Custom LiteLLM endpoint.                                                            |
| `REGISTRY_AUTH`    | GHCR pulls     | Keys inside secret: `REGISTRY_USERNAME`, `REGISTRY_PASSWORD` (GHCR PAT with `read:packages`). |

### Processor-Specific Secrets

Secrets are defined in the registry YAML under `secrets.required`:

```yaml
# code/apps/core/registry/processors/llm_litellm.yaml
name: llm/litellm@1
secrets:
  required: [OPENAI_API_KEY]
```

Additional secrets can be added as needed for new processors.

### Environment & Fingerprinting

The `env_fingerprint` records **only the names** of present environment variables, never their values:

```json
{
  "adapter": "modal",
  "env_keys_present": ["OPENAI_API_KEY", "LITELLM_API_BASE"],
  "modal_env": "dev"
}
```

This ensures deterministic execution while maintaining security.

### Rationale

**Same names across environments** enable running **identical code** in dev/staging/main. Environment isolation is achieved via Modal environments selected at deploy/invoke time (e.g., `--env dev` and `environment_name="dev"`).

## Django Settings Structure

```
code/backend/settings/
├── __init__.py
├── base.py          # Common settings
├── development.py   # Local development  
├── test.py         # CI/CD with PostgreSQL
├── unittest.py     # Unit tests with SQLite
└── production.py   # Production deployment
```

## Registry Structure

Processor definitions in `code/apps/core/registry/processors/`:

```yaml
name: llm/litellm@1
image:
  oci: ghcr.io/veyorokon/llm_litellm@sha256:...
build:
  context: apps/core/processors/llm_litellm
  dockerfile: Dockerfile
runtime:
  cpu: "1"
  memory_gb: 2
  timeout_s: 60
secrets:
  required: [OPENAI_API_KEY]
```

Registry references use the format `{namespace}/{name}@{version}` (e.g., `llm/litellm@1`).
