# Modal Deployment & Secrets (Digest-only)

Modal runs your processor containers as FastAPI web apps via WebSocket protocol. Deployments are pinned to image digests.

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

Canonical slug: `llm/litellm@1` → `llm-litellm-v1`.

**Environment-specific naming:**
- **Dev**: `{branch}-{user}-{ref_slug}` (e.g., `feat-websocket-veyorokon-llm-litellm-v1`)
- **Staging/Main**: `{ref_slug}` (e.g., `llm-litellm-v1`)

**Required environment variables for dev:**
- `GIT_BRANCH`: Git branch name (configured in Django development settings)
- `GIT_USER`: Git username (configured in Django development settings)

## Deploying Processors

### Standard Workflow

**Order of operations:**
1. **Build**: Multi-platform images
2. **Push**: To registry
3. **Pin**: Digest to registry.yaml
4. **Start**: Deploy to Modal
5. **Sync Secrets**: Separately from deployment
6. **Run**: Invoke processor

Modal requires amd64 images. Local development on arm64 (Mac M1/M2) requires arm64 images. Build and pin both platforms:

```bash
# 1. Build both platforms
python manage.py processorctl build \
  --ref llm/litellm@1 \
  --platforms linux/amd64,linux/arm64

# 2. Push to registry
python manage.py processorctl push \
  --ref llm/litellm@1 \
  --platforms linux/amd64,linux/arm64

# 3. Pin amd64 digest (for Modal deployment)
python manage.py processorctl pin \
  --ref llm/litellm@1 \
  --platform amd64 \
  --oci ghcr.io/veyorokon/theory-api/llm-litellm@sha256:a4f41889c246f1f0...

# 4. Pin arm64 digest (for local Mac development)
python manage.py processorctl pin \
  --ref llm/litellm@1 \
  --platform arm64 \
  --oci ghcr.io/veyorokon/theory-api/llm-litellm@sha256:f41c4e79e5871356...
```

After pinning, `registry.yaml` contains both platform digests:
```yaml
image:
  platforms:
    amd64: ghcr.io/veyorokon/theory-api/llm-litellm@sha256:a4f41889c246f1f0...
    arm64: ghcr.io/veyorokon/theory-api/llm-litellm@sha256:f41c4e79e5871356...
```

### Deploy to Modal

```bash
# 1. Deploy by amd64 digest (Modal uses amd64)
GIT_BRANCH=feat/websocket-standardization GIT_USER=veyorokon \
  python manage.py modalctl start \
    --ref llm/litellm@1 \
    --env dev \
    --oci ghcr.io/veyorokon/theory-api/llm-litellm@sha256:a4f41889c246f1f0...

# 2. Sync required secrets (must be done after deployment)
python manage.py modalctl sync-secrets \
  --ref llm/litellm@1 \
  --env dev

# 3. Run processor
python manage.py modalctl run \
  --ref llm/litellm@1 \
  --mode mock \
  --inputs-json '{"schema":"v1","params":{"messages":[{"role":"user","content":"test"}]}}' \
  --json
```

**Critical:**
- Dev environment requires `GIT_BRANCH` and `GIT_USER` environment variables for app naming
- Secrets must be synced separately after deployment (no longer injected at deploy time)
- Use `modalctl start` (not `modalctl deploy`)

### Management Commands

```bash
# Verify pinned digest matches deployed digest
python manage.py modalctl verify-digest \
  --ref llm/litellm@1 \
  --env dev \
  --oci ghcr.io/...@sha256:...

# View deployment status
python manage.py modalctl status --ref llm/litellm@1 --env dev

# View logs
python manage.py modalctl logs --ref llm/litellm@1 --env dev --follow

# Stop deployment
python manage.py modalctl stop --ref llm/litellm@1 --env dev

# Sync secrets with fail-on-missing
python manage.py modalctl sync-secrets \
  --ref llm/litellm@1 \
  --env staging \
  --fail-on-missing
```

### CI/CD Pipeline

1) Build & push multi-arch images (amd64 + arm64)
2) Pin both digests into per-processor `registry.yaml`
3) Deploy by amd64 digest to Modal via `modalctl start`
4) Sync secrets via `modalctl sync-secrets`
5) Verify deployment digest matches registry

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

- {doc}`cli` – `processorctl`, `localctl`, and `modalctl` commands
- {doc}`../concepts/adapters` – Adapter WebSocket transport behaviour
- {doc}`../runbooks/ci-cd` – Pipeline stages for build, pin, deploy-by-digest
