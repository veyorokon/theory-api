# CI/CD Pipeline

Automated build, test, and deployment pipeline for Theory API with processor image management and Modal function deployment.

## Pipeline Overview

```{mermaid}
graph TD
    A[Pull Request] --> B[Unit Tests]
    B --> C[Docs Build]
    C --> D[Lint & Type Check]
    D --> E[Merge to Main]
    E --> F[Detect Changes]
    F --> G[Build Processor Images]
    F --> H[Ensure Secrets]
    F --> I[Deploy Modal Functions]
    G --> J[Pin Image Digests]
    J --> K[Bot PR]
    H --> L[Update Functions]
    I --> L
    L --> M[App Deployment]
```

## Pull Request Checks

### Required Status Checks

All PRs must pass these checks before merge (Fast Lane):

1. **Unit Tests (SQLite)**
   ```bash
   make test-unit
   # Equivalent to: pytest -q -m "unit and not integration and not requires_postgres"
   ```

2. **Documentation Build & Drift Check**
   ```bash
   make docs
   # Runs: docs_export → drift check → sphinx build with -W (warnings fail)
   ```

3. **Lint & Type Checks** (if configured)
   ```bash
   # Example targets
   make lint
   make typecheck
   ```

### PR Template Validation

PRs must use `.github/pull_request_template.md` and complete:
- **Linked Issue**: Reference to GitHub issue
- **Summary**: 1-3 line description
- **Documentation**: List of updated docs files
- **Testing**: Smoke test commands
- **Safety**: Backout steps

## CI Lanes

- **Fast lane (unit + docs):** Runs on every PR and on pushes to `dev`/`main`. Platform‑agnostic (no Docker).
- **Docker lane (acceptance + property):** Runs on Ubuntu with Docker. Triggers on pushes to `dev`/`main` and on PRs labeled `run-acceptance`.

Add the `run-acceptance` label to a PR to execute Docker‑based tests before merge.

## Main Branch Pipeline

### 1. Processor Image Build (0023)

**Trigger**: Changes under `code/apps/core/processors/**`

**Process**:
1. Detect modified processor directories
2. Build linux/amd64 images for each processor
3. Push to GitHub Container Registry (GHCR)
4. Capture image SHA256 digests
5. Create bot PR updating `image.oci` in registry YAML files

**Example**:
```yaml
# Before (registry YAML)
image:
  oci: ghcr.io/veyorokon/llm_litellm:latest

# After (bot PR)
image:
  oci: ghcr.io/veyorokon/llm_litellm@sha256:09e1fb31078db18369fa50c393ded009c88ef880754dbfc1131d750ce3f8f225
```

### 2. Secrets Ensure (Per Environment)

**Trigger**: Registry YAML changes or manual dispatch

**Purpose**: Idempotent secret creation/updates for each Modal environment

**Process**:
```bash
# For each environment (dev, staging, main)
modal secret create REGISTRY_AUTH \
  --from-literal REGISTRY_USERNAME="$GITHUB_USERNAME" \
  --from-literal REGISTRY_PASSWORD="$GITHUB_PAT"

modal secret create OPENAI_API_KEY \
  --from-literal OPENAI_API_KEY="$OPENAI_API_KEY"

modal secret create LITELLM_API_BASE \
  --from-literal LITELLM_API_BASE="$LITELLM_API_BASE"
```

**Secret Sources**: CI secret store provides environment-specific values

### 3. Modal Function Deployment (Committed Module)

**Trigger**: Registry YAML changes (image/runtime/secrets modifications)

**Process**:
```bash
# For each environment
export PROCESSOR_REF=llm/litellm@1
export IMAGE_REF=ghcr.io/veyorokon/llm_litellm@sha256:...
export TOOL_SECRETS=OPENAI_API_KEY
python manage.py sync_modal --env $MODAL_ENV
```

**Validation**: Functions deployed successfully and accessible

### 4. Application Deployment

**Final step**: Deploy Django application with updated processor registry

## Environment-Specific Workflows

### Development Environment

**Secrets**: Development API keys and test credentials
**Modal App**: `theory-rt`
**Registry**: Uses same image digests as main, different secret values

### Staging Environment

**Secrets**: Staging API keys (often same as main)
**Modal App**: `theory-rt`  
**Registry**: Pre-production validation before main deployment

### Main Environment

**Secrets**: Production API keys
**Modal App**: `theory-rt`
**Registry**: Authoritative processor definitions

## Pipeline Triggers

### Automatic Triggers

| Change Type | Trigger | Jobs |
|-------------|---------|------|
| Processor source code | Push to main | Build images → Pin digests → Deploy functions |
| Registry YAML updates | Push to main | Ensure secrets → Deploy functions |
| Documentation changes | Push to main | Build & deploy docs |
| Any code changes | Pull request | Unit tests → Docs build → Lint |

### Manual Triggers

| Workflow | Purpose | When to Use |
|----------|---------|-------------|
| Secrets Ensure | Update/create secrets | New environment setup, secret rotation |
| Function Deploy | Redeploy Modal functions | Function issues, registry rollback |
| Full Pipeline | Complete rebuild | Major version deployment |

## Configuration Files

### GitHub Actions

```
.github/workflows/
├── ci-cd.yml           # Main CI/CD pipeline
├── docs.yml            # Documentation build
├── processor-build.yml # Processor image builds
└── modal-deploy.yml    # Modal function deployment (single committed module)
```

### Pipeline Secrets

Required in GitHub repository secrets:

| Secret | Purpose | Environments |
|--------|---------|--------------|
| `GITHUB_PAT` | GHCR access, bot PRs | All |
| `MODAL_TOKEN_ID` / `MODAL_TOKEN_SECRET` | Modal API access | All |
| `OPENAI_API_KEY_DEV` | Development OpenAI | Development |
| `OPENAI_API_KEY_MAIN` | Production OpenAI | Staging, Production |

## Deployment Order

**Critical**: Maintain correct deployment sequence per environment:

1. **Create/verify secrets** (names identical across environments)
2. **Ensure image digests pinned** in registry YAML
3. **Deploy Modal functions** with `sync_modal --env <env>`
4. **Deploy application** with updated registry
5. **Verify functionality** with smoke tests

## Rollback Procedures

### Registry Rollback

```bash
# 1. Revert registry YAML to previous digest
git revert <commit-hash>

# 2. Redeploy Modal functions
export PROCESSOR_REF=llm/litellm@1
export IMAGE_REF=ghcr.io/veyorokon/llm_litellm@sha256:...
python manage.py sync_modal --env main

# 3. Deploy application
# (application deployment process)
```

### Secret Rollback

```bash
# Update secret with previous value
modal secret update OPENAI_API_KEY \
  --from-literal OPENAI_API_KEY="$PREVIOUS_API_KEY"
```

### Function Rollback

```bash
# Redeploy with previous registry state
export PROCESSOR_REF=llm/litellm@1
export IMAGE_REF=ghcr.io/veyorokon/llm_litellm@sha256:prev...
python manage.py sync_modal --env main
```

## Monitoring & Alerts

### Pipeline Health

- **Build failures**: Alert on processor image build failures
- **Deployment failures**: Alert on Modal function deployment issues
- **Test failures**: Block merges on failing unit tests or docs builds
- **Secret issues**: Monitor secret access failures in Modal

### Performance Metrics

- **Build times**: Track processor image build duration
- **Deployment times**: Monitor Modal function deployment speed
- **Test execution**: Track test suite performance over time

## Troubleshooting

### Common Pipeline Issues

**"invalid username/password" in processor build:**
- Check GitHub PAT in `GITHUB_PAT` secret
- Verify PAT has `read:packages` and `write:packages` scopes

**"function not found" after deployment:**
- Ensure deployment ran to the correct environment (`--env dev|staging|main`)
- Function name is derived from processor ref: `exec__{slug}__v{ver}`
- Verify Modal deployment completed successfully

**Unit tests failing on PR:**
- Run tests locally: `make test-unit`
- Check for database migration issues
- Verify test environment setup

**Docs build failures:**
- Missing referenced documents in toctree
- Cross-reference syntax errors
- Generated content drift (run `make docs` locally)

### Debug Commands

**Check CI status:**
```bash
gh workflow list
gh run list --workflow=ci-cd.yml
```

**Test locally:**
```bash
make test-unit
make docs
python manage.py run_processor --ref llm/litellm@1 --adapter local --write-prefix /artifacts/outputs/text/ --inputs-json '{}'
```

**Modal debugging:**
```bash
modal app list
modal function list --app theory-rt
modal logs --app theory-rt
```

## Cross-References

- {doc}`../guides/modal` - Modal deployment and secrets management
- {doc}`../guides/tests` - Test matrix and execution details
- {doc}`deployments` - Manual deployment procedures
- [ADR-0003: Branch Strategy CI/CD](../adr/ADR-0003-branch-strategy-cicd.md) - CI/CD design decisions
