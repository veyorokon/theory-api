# CI/CD Runbook

This document provides operational guidance for the Theory Runtime CI/CD system, covering lanes, workflows, troubleshooting, and maintenance procedures.

## Overview

The CI/CD system uses a **build-once, deploy-many** strategy with digest pinning to ensure "test the bits you ship" consistency across environments.

### Core Principles

- **Fast feedback loops**: Separate fast (unit tests, docs) from slow (acceptance, Docker) lanes
- **Digest pinning**: All production deployments use pinned SHA256 digests, not floating tags
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
- `code/apps/core/registry/processors/**`

**Runtime**: ~3-5 minutes per processor
**Runs on**: `ubuntu-latest`

```yaml
# .github/workflows/build-and-pin.yml
- Discover changed processors (paths-filter)
- Build Docker images (linux/amd64)
- Push to GHCR with SHA tag
- Extract digest from registry
- Create bot PR pinning digest in registry YAML
```

**Purpose**: Automated image building with digest pinning for reproducible deployments.

### 4. Modal Deploy Lane
**Trigger**: Push to `dev`, `staging`, `main` branches
**Runtime**: ~1-2 minutes
**Runs on**: `ubuntu-latest`

```yaml
# .github/workflows/modal-deploy.yml
- Extract pinned digest from registry
- Deploy committed module: modal deploy -m modal_app
- Post-deploy smoke test
```

**Purpose**: Environment-gated deployments to Modal with smoke testing.

### 5. Rollback Workflow
**Trigger**: Manual workflow_dispatch only
**Runtime**: ~2-3 minutes

```yaml
# .github/workflows/rollback.yml
- Checkout target commit
- Validate registry state at target
- Deploy rollback to Modal
- Smoke test rollback deployment
```

**Purpose**: Emergency rollback to previous known-good state.

### 6. Environment Drift Audit
**Trigger**: Weekly schedule (Monday 09:00 UTC) + manual dispatch
**Runtime**: ~1-2 minutes per environment

```yaml
# .github/workflows/audit-env.yml  
- Query Modal apps per environment
- Compare deployed vs expected state
- Generate audit reports
- Create/update GitHub issue with findings
```

**Purpose**: Detect configuration drift between expected and deployed state.

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
- **App naming**: `{slug}-{version}-{environment}`
  - Example: `llm-litellm-v1-dev`
- **Function naming**: `run` (single function per app)
- **Environment mapping**: 
  - `dev` → `dev`
  - `staging` → `staging`  
  - `main` → `main` (production)

### Image References
- **During build**: `ghcr.io/owner/llm-litellm:sha-{commit}`
- **After pinning**: `ghcr.io/owner/llm-litellm@sha256:{digest}`
- **Registry storage**: `image.oci` field in `code/apps/core/registry/processors/{processor}.yaml`

## Operational Procedures

### Image Pin Workflow
1. **Automated trigger**: Push changes to processor paths
2. **Build process**: 
   - Detect changed processors via paths-filter
   - Build and push Docker images to GHCR
   - Extract SHA256 digest from registry
3. **Pin creation**: 
   - Bot creates PR updating registry YAML
   - PR title: `Pin digest for {processor} @ {commit}`
   - Auto-labeled: `registry`, `automation`
4. **Review and merge**: Human reviews and merges pin PR
5. **Deployment**: Next Modal deploy uses pinned digest

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
1. **Weekly report**: Review automated audit issue created Mondays
2. **Investigate discrepancies**:
   - Missing apps: Check deployment pipeline health
   - Version mismatches: Verify pin PR workflow  
   - Access errors: Validate Modal credentials
3. **Remediation**:
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
# Get current pinned image
make ci-get-image-ref

# Test adapter parity
DJANGO_SETTINGS_MODULE=backend.settings.unittest \
python manage.py run_processor \
  --ref llm/litellm@1 \
  --adapter mock \
  --write-prefix /artifacts/outputs/test/{execution_id}/ \
  --inputs-json '{"messages":[{"role":"user","content":"test"}]}' \
  --json
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

## Helper Scripts

The following scripts are available in `scripts/ci/` for operational tasks:

### `get_image_ref.py`
```bash
# Extract current pinned image reference
python scripts/ci/get_image_ref.py
# Output: ghcr.io/owner/llm-litellm@sha256:abc123...
```

### `pin_processor.py`  
```bash
# Pin processor to specific digest
python scripts/ci/pin_processor.py llm_litellm \
  ghcr.io/owner/llm-litellm \
  sha256:abc123...
```

### Makefile Integration
```bash
# Get current pinned reference
make ci-get-image-ref

# Pin processor (for manual operations)
make ci-pin-processor PROCESSOR=llm_litellm \
  IMAGE_BASE=ghcr.io/owner/llm-litellm \
  DIGEST=sha256:abc123...
```

---

*This runbook is maintained by the Platform Engineering team. For updates or questions, see the [CI/CD Architecture Decision Records](../decisions/adr-ci-cd.md).*