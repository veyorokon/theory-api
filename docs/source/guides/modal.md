# Modal Deployment & Secrets

Modal provides serverless execution for processors using a committed module (`code/modal_app.py`). This guide reflects the updated naming and control flow: **modes are explicit** and **app names are deterministic**.

## Secrets Policy

The authoritative secrets standard for Modal integration.

### Core Principle

Secret names match the environment variables consumed by processors (`OPENAI_API_KEY`, `REGISTRY_AUTH`, etc.). Names stay the same across all environments; only values differ.

### Required Secrets

| Secret | Keys | Purpose |
|--------|------|---------|
| `REGISTRY_AUTH` | `REGISTRY_USERNAME`, `REGISTRY_PASSWORD` | GHCR image pulls |
| `OPENAI_API_KEY` | `OPENAI_API_KEY` | Real-mode LLM calls |
| `LITELLM_API_BASE` | `LITELLM_API_BASE` | Optional custom LiteLLM endpoint |

Example creation:

```bash
modal secret create REGISTRY_AUTH \
  --from-literal REGISTRY_USERNAME="$GITHUB_USERNAME" \
  --from-literal REGISTRY_PASSWORD="$GITHUB_PAT"

modal secret create OPENAI_API_KEY \
  --from-literal OPENAI_API_KEY="$OPENAI_API_KEY"
```

## Processor App Naming

We rely on a single source of truth, `modal_app_name_from_ref()`, which maps `llm/litellm@1` → **`llm-litellm-v1`**.

- **CI/CD** (`modal deploy -m modal_app` with `PROCESSOR_REF` set): app name is exactly the processor name (`llm-litellm-v1`, `replicate-generic-v1`). The Modal environment (`--env dev|staging|main`) scopes deployments, so no suffix is needed.
- **Human management commands** (e.g., `deploy_modal`, `logs_modal`): we derive `user-branch-{processor}` via `_modalctl.resolve_app_name` so personal sandboxes stay distinct (`veyorokon-dev-llm-litellm-v1`). Pass `--app-name` to override.

## Deploying Processors

### CI/CD pipeline

The deploy workflow simply runs:

```bash
modal deploy -m modal_app --env "$MODAL_ENVIRONMENT"
```

`PROCESSOR_REF`, `IMAGE_REF`, and `TOOL_SECRETS` are exported in the job environment. `modal_app.py` reads them, names the app (`llm-litellm-v1`), and registers the function.

After deploy, a smoke test calls the `smoke` function with `mode="mock"`.

### Local / manual usage

Developer-friendly Django commands use `_modalctl.resolve_app_name` for sandbox names:

```bash
python manage.py deploy_modal --env dev --ref llm/litellm@1 \
    --image ghcr.io/.../llm-litellm@sha256:... \
    --secrets OPENAI_API_KEY

# App is veyorokon-<branch>-llm-litellm-v1 (automatically resolved)
```

To inspect logs or call functions manually:

```bash
python manage.py logs_modal --env dev --ref llm/litellm@1
python manage.py invoke_modal --env dev --ref llm/litellm@1 --payload-json '{"schema":"v1","mode":"mock","params":{...}}'
```

## Modes & Payloads

Processors look at `inputs["mode"]`:

- `mode="mock"`: deterministic responses; used by CI smoke tests and local quick checks.
- `mode="real"`: hits external providers; secrets must exist (e.g., `OPENAI_API_KEY`).

Modal smoke functions force `mode="mock"`; real production jobs pass `mode="real"`.

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `ERR_MISSING_SECRET` | Ensure required secret exists in the target Modal environment. |
| `Image pull failed` | Verify `REGISTRY_AUTH` values and the pinned `image.oci` digest. |
| Function not found | Confirm the processor ref was deployed for that Modal env (`modal app list --env dev`). |

Example checks:

```bash
modal app list --env dev
modal function list --app llm-litellm-v1 --env dev
modal logs --app llm-litellm-v1 --env dev
```

## Cross-References

- {doc}`cli` – `run_processor` (`--mode mock|real`) and Modal management commands
- {doc}`../concepts/adapters` – Adapter behaviour for mock vs real mode
- {doc}`../runbooks/ci-cd` – Pipeline stages for build, acceptance, and deploy
