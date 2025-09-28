# Modal Deployment & Secrets (Digest-only)

Modal runs your processor containers as FastAPI web apps. Deployments are pinned to image digests.

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

Canonical slug: `llm/litellm@1` → `llm-litellm-v1`. Dev env may prefix with `branch-user-`.

## Deploying Processors

### CI/CD pipeline

1) Build & push image; capture amd64 digest
2) Pin digest into per-processor `registry.yaml`
3) Deploy by digest; verify deployment digest

CLI:

```bash
# Deploy by digest
python manage.py modalctl deploy --ref llm/litellm@1 --env dev --oci ghcr.io/...@sha256:...

# Verify pinned digest bound to app
python manage.py modalctl verify-digest --ref llm/litellm@1 --env dev --oci ghcr.io/...@sha256:...

# Status / logs
python manage.py modalctl status --ref llm/litellm@1 --env dev
python manage.py modalctl logs --ref llm/litellm@1 --env dev

# Sync required secrets (names from registry.yaml)
python manage.py modalctl sync-secrets --ref llm/litellm@1 --env staging --fail-on-missing
```

## Modes & Payloads

Processors receive `payload.mode`:

- `mock`: deterministic responses; used by PR smoke and local acceptance
- `real`: external calls; required secrets must be present

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `ERR_MISSING_SECRET` | Ensure required secret exists in the target Modal environment. |
| `Image pull failed` | Verify registry auth and pinned digest. |
| Function not found | Confirm the app exists in the target env and is named correctly. |

Example checks:

```bash
modal app list --env dev
modal function list --app llm-litellm-v1 --env dev
modal logs --app llm-litellm-v1 --env dev
```

## Cross-References

- {doc}`cli` – `run_processor` and `modalctl` commands
- {doc}`../concepts/adapters` – Adapter HTTP transport behaviour
- {doc}`../runbooks/ci-cd` – Pipeline stages for build, pin, deploy-by-digest
