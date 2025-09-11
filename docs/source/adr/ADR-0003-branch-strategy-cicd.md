# ADR-0003 — Branch Strategy and CI/CD Pipeline

- **Status:** Accepted
- **Date:** 2025-09-05  
- **Deciders:** Engineering Team
- **Technical Story:** Repository branching and deployment automation

## Context

Theory API requires:
- Safe production deployments with review gates
- Environment isolation (dev/staging/prod) 
- Integration with existing AWS ECS + Terraform infrastructure
- Enforcement of docs-as-contracts governance workflow

Current state: Single `main` branch, no automated deployments, manual infrastructure management.

## Decision

**Branch Strategy:**
- `main` (production) - Protected, requires reviews, deploys to prod ECS
- `staging` - Integration testing, deploys to staging ECS  
- `dev` - Active development, deploys to dev ECS
- Feature branches: `feat/area-description`, `fix/area-description`

**CI/CD Pipeline (GitHub Actions):**
- PR validation: tests + linting + docs build
- Branch deployments: `dev`→dev ECS, `staging`→staging ECS, `main`→prod ECS
- Docker build → ECR push → ECS service update
- Terraform state managed in S3 (per existing `infra/` structure)

**Protection Rules:**
- `main`: Require 1+ reviews, status checks, no force push, linear history
- `staging`: Require status checks, allow fast-forward merges
- `dev`: Minimal restrictions, allow direct pushes for rapid iteration

### Environment Protection & Self-Approval (Sole Maintainer Mode)
- **development**: no reviewers (auto-deploy)
- **staging**: reviewer required → **sole maintainer self-approval**
- **production**: reviewer required → **sole maintainer self-approval** (promote to two-person rule when team grows)
- Approvals performed via GitHub UI or CLI (`gh api ... pending_deployments`) with full audit trail

## Consequences

### Positive
- Safe production deployments with human oversight
- Automated testing prevents regression
- Environment parity reduces deployment surprises
- Integration with existing infrastructure investment
- Explicit self-approval policy avoids blocking solo workflows while preserving auditability

### Negative
- Additional CI/CD complexity and AWS costs
- Longer feedback cycles due to review requirements
- Initial setup overhead for workflows and secrets

### Neutral
- Branch protection may slow emergency fixes (mitigate with hotfix process)
- GitHub Actions minutes usage (monitor and budget)

## Alternatives Considered

### Option A: GitFlow
- **Pros:** Well-established pattern with develop/release branches
- **Cons:** Overkill for team size, conflicts with docs-governance simplicity
- **Rejected because:** Additional complexity without benefit

### Option B: Trunk-based Development  
- **Pros:** Simple workflow, direct commits to main with feature flags
- **Cons:** Insufficient safety gates for production system
- **Rejected because:** Lacks review process and deployment controls

### Option C: Manual Deployments
- **Pros:** Simple, no automation complexity
- **Cons:** Doesn't scale, error-prone, blocks automation
- **Rejected because:** Manual process doesn't support team growth

## Implementation

```yaml
# GitHub Actions workflow structure
on:
  push: [main, staging, dev]
  pull_request: [main, staging, dev]

jobs:
  test: # Django tests + docs build
  build: # Docker → ECR push  
  deploy-dev: # ECS update (dev branch)
  deploy-staging: # ECS update (staging branch)
  deploy-production: # ECS update (main branch)
```

## Governance Playbook

All CI/CD changes follow a structured workflow:

1. **Conversation → Issue** - Use CI/CD Change issue template with ADR-0003 label
2. **Issue → PR** - Complete governance checklist in PR template  
3. **Review → Merge** - Branch protection enforces review and status checks
4. **Documentation** - Keep guides/ci-cd.md and this ADR synchronized

### Deployment Safety Gates

- **Environment Variables:** `DEPLOY_ENABLED_DEV/STAGING/PROD` control deployment execution
- **GitHub Environments:** Provide secret isolation and approval requirements
- **Branch Protection:** Production deploys require human review and passing tests

See [CI/CD Operations Guide](../runbooks/ci-cd) for detailed procedures.

## Status History

- 2025-09-05: Proposed during repository setup
- 2025-09-05: Accepted and implemented with GitHub Actions workflow
- 2025-09-05: Enhanced with governance playbook and deployment safety gates