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

`modal_app_name_from_ref()` is the single source of truth. `llm/litellm@1` → **`llm-litellm-v1`**.

- **CI/CD** (`modal deploy -m modal_app` with `PROCESSOR_REF` set): app name is exactly the processor slug (`llm-litellm-v1`, `replicate-generic-v1`). The Modal environment (`--env dev|staging|main`) scopes deployments; no human prefixes.
- **Human management commands** (e.g., `deploy_modal`, `logs_modal`): by default we reuse the same canonical slug. Pass `--app-name` if you truly need a custom sandbox name, or set `MODAL_APP_NAME` before calling `modal deploy`.

## Deploying Processors

### CI/CD pipeline

The deploy workflow simply runs:

```bash
modal deploy -m modal_app --env "$MODAL_ENVIRONMENT"
```

`PROCESSOR_REF`, `IMAGE_REF`, and `TOOL_SECRETS` are exported in the job environment. `modal_app.py` reads them, names the app (`llm-litellm-v1`), and registers the function.

After deploy, a smoke test calls `run_processor … --mode mock` against the Modal adapter. There is a single Modal function (`run`); smoke and canary tests simply choose which mode to pass.

### Local / manual usage

Developer-friendly Django commands take only the processor ref; registry metadata is resolved automatically.

```bash
python manage.py deploy_modal --env dev --ref llm/litellm@1

# App resolves to llm-litellm-v1 (override with --app-name if needed)
```

To inspect logs or execute processors manually:

```bash
python manage.py logs_modal --env dev --ref llm/litellm@1

# Execute processors (single execution surface)
python manage.py run_processor --ref llm/litellm@1 --adapter modal --mode mock \
  --inputs-json '{"schema":"v1","params":{"messages":[{"role":"user","content":"test"}]}}'

python manage.py run_processor --ref llm/litellm@1 --adapter modal --mode real \
  --inputs-json '{"schema":"v1","params":{"messages":[{"role":"user","content":"test"}]}}'
```

## Modes & Payloads

Processors look at `inputs["mode"]`:

- `mode="mock"`: deterministic responses; used by CI smoke tests and local quick checks.
- `mode="real"`: hits external providers; secrets must exist (e.g., `OPENAI_API_KEY`).

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
