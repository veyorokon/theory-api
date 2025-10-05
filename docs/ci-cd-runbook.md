# CI/CD Runbook

This document provides operational guidance for the Theory Runtime CI/CD system, covering lanes, workflows, troubleshooting, and maintenance procedures.

## Overview

The CI/CD system uses a **build-once, deploy-many** strategy with digest pinning to ensure "test the bits you ship" consistency across environments.

### Core Principles

- **Fast feedback loops**: Separate fast (unit tests, docs) from slow (acceptance, Docker) lanes
- **Digest pinning**: All deployments use pinned SHA256 digests, not floating tags
- **Environment parity**: Same secret names and configurations across dev/staging/prod
- **Fail-fast**: Zero retries on Modal functions; let CI handle retry policy
- **Audit trails**: Weekly drift detection between deployed vs expected state

## Workflow Lanes

### 1. Fast Lane (PR Checks)
**Trigger**: All pull requests to `dev`, `staging`, `main`
**Runtime**: ~2-3 minutes
**Runs on**: `ubuntu-latest`

```yaml
# .github/workflows/pr-checks.yml
- Lint (flake8 if present)
- Unit tests (no Docker dependencies)
- Documentation build (fail on warnings)
```

**Purpose**: Immediate feedback for developers; required check for merge.

### 2. Docker Lane (Acceptance & Property)
**Trigger**:
- Push to `dev` branch
- Daily schedule (06:00 UTC)
- Manual dispatch
- PRs with `run-acceptance` label

**Runtime**: ~5-10 minutes
**Runs on**: `ubuntu-latest` (Docker required)

```yaml
# .github/workflows/acceptance.yml
- Docker compose up (postgres, redis, minio)
- Acceptance tests (ledger integration)
- Property-based tests
- Service teardown
```

**Purpose**: Integration testing with real services; optional for PR merge.

### 3. Build & Pin Lane
**Trigger**: Changes to processor code paths:
- `code/apps/core/processors/**`
- `code/libs/**`
- `code/apps/core/processors/**/registry.yaml`

**Runtime**: ~3-5 minutes per processor
**Runs on**: `ubuntu-latest`

```yaml
# .github/workflows/build-and-pin.yml
- Discover changed processors (paths-filter)
- Build multi-platform Docker images (linux/amd64,linux/arm64)
- Push to GHCR: python manage.py processorctl push --ref <ref> --platforms linux/amd64,linux/arm64
- Pin digests: python manage.py processorctl pin --ref <ref> --platform amd64 --oci <digest>
- Create bot PR pinning digests in the processor's registry.yaml
```

**Purpose**: Automated multi-platform image building with digest pinning for reproducible deployments.

### GHCR Package Access & Authentication (Required)

GitHub Actions must be able to pull private images from GitHub Container Registry (GHCR). Link the package to your repo with the correct permission:

1) Repository → Packages → Select package (e.g., `llm_litellm`) → Package settings
2) Repository access → Add repository → Select your repo
3) Choose “Actions: Read” permission (NOT “Codespaces”).

CI authentication (example):
```yaml
- name: Authenticate Docker to GHCR
  run: |
    echo "${{ secrets.GHCR_RO || secrets.GITHUB_TOKEN }}" | \
      docker login ghcr.io -u ${{ github.actor }} --password-stdin
```

Preflight check (optional but recommended):
```yaml
- name: Assert pinned image exists in GHCR
  run: |
    REF=$(make ci-get-image-ref)
    docker manifest inspect "$REF"
```

Distinction: “Codespaces” access is for dev environments; **CI/CD needs “Actions: Read”** so workflows can pull images.

### 4. Modal Deploy Lane
**Trigger**: Push to `dev`, `staging`, `main` branches
**Runtime**: ~1-2 minutes
**Runs on**: `ubuntu-latest`

```yaml
# .github/workflows/modal-deploy.yml
- Extract pinned digest from per-processor registry.yaml
- Deploy by digest: python manage.py modalctl start --ref <ref> --env <env> --oci <digest>
- Sync secrets: python manage.py modalctl sync-secrets --ref <ref> --env <env>
- Post-deploy smoke test: python manage.py modalctl run --ref <ref> --mode mock --json
```

**Purpose**: Environment-gated deployments to Modal with secret sync and smoke testing.

**Critical:**
- Dev environment requires `GIT_BRANCH` and `GIT_USER` environment variables
- Secrets must be synced separately after deployment
- Use `modalctl start` (not `modalctl deploy`)

### 5. Modal Drift Audit
**Trigger**:
- Push to `dev`, `staging`, `main` branches
- Pull requests to `main`
- Manual workflow_dispatch

**Runtime**: ~1-2 minutes
**Behavior**:
- `dev`/`staging`: Report-only (continue-on-error: true)
- `main`: Fail-closed if audit fails
- PRs: Report-only for visibility

```yaml
# .github/workflows/modal-drift.yml
- Resolve expected app/function (app: {slug}-v{ver}-{env}; fn: run)
- Compare against deployed via Modal SDK
- dev/staging: report-only; main: fail-closed
```

**Purpose**: Detect configuration drift between expected and deployed state.

### 6. Manual Rollback
**Available via**: Manual workflow_dispatch or CLI commands
**Runtime**: ~2-3 minutes

**Manual process**:
```bash
# Identify target commit with working deployment
git log --oneline

# Checkout target commit
git checkout <commit-sha>

# Redeploy modal app from target commit
python manage.py modalctl start --ref <ref> --env <env> --oci <digest>

# Sync secrets
python manage.py modalctl sync-secrets --ref <ref> --env <env>

# Verify deployment
python manage.py modalctl run --ref <ref> --mode mock --json
```

**Purpose**: Emergency rollback to previous known-good state.

## Secret Management

### GitHub Repository Secrets
```
MODAL_TOKEN_ID          # Modal authentication (CI deployments)
MODAL_TOKEN_SECRET      # Modal authentication (CI deployments)
OPENAI_API_KEY_DEV      # Development workload key
```

### Modal Secrets (per environment)
```
REGISTRY_AUTH           # GHCR authentication (image pulls)
├── REGISTRY_USERNAME   # GitHub actor
└── REGISTRY_PASSWORD   # GitHub token with packages:read

OPENAI_API_KEY          # Workload runtime key
```

**Important**: Secret names in Modal must match environment variable names exactly.

## Naming Conventions

### Modal Resources
- **App naming**:
  - **Dev**: `{branch}-{user}-{ref_slug}` (e.g., `feat-websocket-veyorokon-llm-litellm-v1`)
  - **Staging/Main**: `{ref_slug}` (e.g., `llm-litellm-v1`)
- **Function naming**: `fastapi_app` (FastAPI WebSocket endpoint)
- **Environment mapping**:
  - `dev` → `dev` (requires GIT_BRANCH and GIT_USER)
  - `staging` → `staging`
  - `main` → `main` (production)

### Image References
- **During build**: `ghcr.io/owner/llm-litellm:sha-{commit}`
- **After pinning**: `ghcr.io/owner/llm-litellm@sha256:{digest}`
- **Registry storage**: `image.platforms.{amd64,arm64}` in `code/apps/core/processors/<ns>_<name>/registry.yaml`

## Operational Procedures

### Image Pin Workflow
1. **Automated trigger**: Push changes to processor paths
2. **Build process**:
   - Detect changed processors via paths-filter
   - Build multi-platform images: `python manage.py processorctl build --ref <ref> --platforms linux/amd64,linux/arm64`
   - Push to GHCR: `python manage.py processorctl push --ref <ref> --platforms linux/amd64,linux/arm64`
   - Extract SHA256 digests for both platforms
3. **Pin creation**:
   - Pin amd64: `python manage.py processorctl pin --ref <ref> --platform amd64 --oci <digest>`
   - Pin arm64: `python manage.py processorctl pin --ref <ref> --platform arm64 --oci <digest>`
   - Bot creates PR updating registry YAML with both platform digests
   - PR title: `Pin digest for {processor} @ {commit}`
   - Auto-labeled: `registry`, `automation`
4. **Review and merge**: Human reviews and merges pin PR
5. **Deployment**: Modal deploy uses pinned amd64 digest via `python manage.py modalctl start --ref ... --env ... --oci ...`

### Rollback Procedure
1. **Identify target**: Determine commit SHA of known-good state
2. **Validate target**: Ensure target commit has valid pinned registry
3. **Execute rollback**:
   ```bash
   # Via GitHub UI: Actions → Rollback Deployment
   # Inputs:
   # - environment: dev|staging|prod
   # - previous_commit: <commit-sha>
   ```
4. **Verify deployment**: Check smoke test results
5. **Update tracking**: Coordinate with team on branch state

### Drift Audit Response
1. **Continuous monitoring**: Drift checks run on every push/PR
2. **Environment-specific behavior**:
   - **dev/staging**: Drift reported but doesn't block deployment
   - **main**: Drift failures block deployment for safety
3. **Investigate discrepancies**:
   - Missing apps: Check deployment pipeline health
   - Version mismatches: Verify pin PR workflow
   - Access errors: Validate Modal credentials
4. **Remediation**:
   - Re-trigger deployments if needed
   - Update broken workflows
   - Escalate credential issues

### Environment Debugging

#### Modal CLI Debugging
```bash
# List apps in environment
modal app list --env dev

# Check specific function
modal function logs <app-name>::run --env dev

# Test function directly
modal run --env dev -m modal_app --input '{"test": true}'
```

#### Local Testing
```bash
# Start local container
OPENAI_API_KEY=$OPENAI_API_KEY python manage.py localctl start --ref llm/litellm@1

# Test local adapter
python manage.py localctl run \
  --ref llm/litellm@1 \
  --mode mock \
  --inputs-json '{"schema":"v1","params":{"messages":[{"role":"user","content":"test"}]}}' \
  --json

# Stop container
python manage.py localctl stop --ref llm/litellm@1
```

#### CI Workflow Debugging
```bash
# Check workflow status
gh run list --workflow="Modal Deploy"

# View specific run logs
gh run view <run-id> --log

# Re-trigger failed workflow
gh run rerun <run-id>
```

## Troubleshooting Guide

### Common Issues

#### "Missing pinned image reference"
- **Symptom**: Modal deploy fails with unpinned image error
- **Cause**: Registry YAML has floating tag instead of digest
- **Fix**: Ensure build-and-pin workflow completed; check for open pin PRs

#### "Modal function not found"
- **Symptom**: Adapter can't resolve function by name
- **Cause**: App naming mismatch or deployment failure
- **Fix**: Verify app name construction; check Modal deploy workflow logs

#### "Docker services failed to start"
- **Symptom**: Acceptance tests fail with connection errors
- **Cause**: Docker compose issues or port conflicts
- **Fix**: Check Docker daemon status; verify compose file syntax

#### "Secrets not accessible in Modal"
- **Symptom**: Runtime errors accessing API keys
- **Cause**: Secret naming mismatch or missing Modal secrets
- **Fix**: Verify secret names match env vars; check Modal web console

### Recovery Procedures

#### Failed Deployment Recovery
1. Check deployment logs for specific error
2. If image-related: Wait for or trigger build-and-pin workflow
3. If secrets-related: Verify Modal secret configuration
4. If persistent: Execute rollback to last known-good commit

#### CI Pipeline Recovery
1. **Workflow failures**: Re-run failed jobs via GitHub UI
2. **Credential issues**: Rotate and update repository secrets
3. **Runner issues**: Check GitHub Status page for service issues

## Monitoring and Alerts

### Key Metrics
- **Fast lane success rate**: Should be >95%
- **Build-and-pin latency**: Should complete within 10 minutes
- **Modal deploy success rate**: Should be >98%
- **Drift detection frequency**: Weekly audit completion

### Alert Conditions
- Consecutive fast lane failures (>3)
- Build-and-pin workflow failures
- Modal deploy failures to production
- Drift audit detects missing deployments

## Maintenance Tasks

### Weekly
- Review drift audit reports
- Check for stale pin PRs awaiting review
- Verify Modal token expiration dates

### Monthly
- Review workflow run history for patterns
- Update documentation for any process changes
- Audit Modal secret rotation needs

### Quarterly
- Review and update GitHub runner specifications
- Evaluate CI/CD metrics and optimization opportunities
- Update Modal CLI and action versions

---

## Management Commands Reference

All CI/CD operations use Django management commands for consistency:

### processorctl - Image Operations
```bash
# Build multi-platform images
python manage.py processorctl build --ref llm/litellm@1 --platforms linux/amd64,linux/arm64

# Push to registry
python manage.py processorctl push --ref llm/litellm@1 --platforms linux/amd64,linux/arm64

# Pin platform-specific digests
python manage.py processorctl pin --ref llm/litellm@1 --platform amd64 --oci ghcr.io/...@sha256:...
python manage.py processorctl pin --ref llm/litellm@1 --platform arm64 --oci ghcr.io/...@sha256:...
```

### localctl - Local Runtime
```bash
# Start container (secrets from environment)
OPENAI_API_KEY=$OPENAI_API_KEY python manage.py localctl start --ref llm/litellm@1

# Run processor
python manage.py localctl run --ref llm/litellm@1 --mode mock --json

# Stop container
python manage.py localctl stop --ref llm/litellm@1
```

### modalctl - Modal Runtime
```bash
# Deploy to Modal
GIT_BRANCH=feat/test GIT_USER=veyorokon \
python manage.py modalctl start --ref llm/litellm@1 --env dev --oci ghcr.io/...@sha256:...

# Sync secrets
python manage.py modalctl sync-secrets --ref llm/litellm@1 --env dev

# Run processor
python manage.py modalctl run --ref llm/litellm@1 --mode mock --json

# Stop deployment
python manage.py modalctl stop --ref llm/litellm@1 --env dev
```

---

*This runbook is maintained by the Platform Engineering team. For updates or questions, see the [CI/CD Architecture Decision Records](../decisions/adr-ci-cd.md).*
