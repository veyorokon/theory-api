# Deployment Runbook (Sole Maintainer)

## Environment Configuration

- **development**: auto-deploy (no reviewers required)
- **staging**: deployment gated, reviewer = sole maintainer
- **production**: deployment gated, reviewer = sole maintainer (promote to two-person rule when team grows)

## One-Time Setup: Configure Environment Reviewers

```bash
# Get your GitHub user ID
GH_USER_ID=$(gh api user --jq '.id')

# Configure environments
gh api --method PUT repos/veyorokon/visureel-api/environments/development \
  -F wait_timer=0

gh api --method PUT repos/veyorokon/visureel-api/environments/staging \
  -F wait_timer=0 \
  -F reviewers="[{\"type\":\"User\",\"id\":$GH_USER_ID}]"

gh api --method PUT repos/veyorokon/visureel-api/environments/production \
  -F wait_timer=30 \
  -F reviewers="[{\"type\":\"User\",\"id\":$GH_USER_ID}]"
```

## Approve Pending Deployment (CLI)

When a deployment is waiting for approval:

```bash
# Get the latest run ID for current branch
RUN_ID=$(gh run list --limit 1 --json databaseId -q '.[0].databaseId')

# Get environment ID (staging or production)
STAGING_ENV_ID=$(gh api repos/veyorokon/visureel-api/environments --jq '.environments[] | select(.name=="staging") | .id')
PROD_ENV_ID=$(gh api repos/veyorokon/visureel-api/environments --jq '.environments[] | select(.name=="production") | .id')

# View pending deployments
gh api repos/veyorokon/visureel-api/actions/runs/$RUN_ID/pending_deployments | jq

# Approve staging deployment
gh api -X POST repos/veyorokon/visureel-api/actions/runs/$RUN_ID/pending_deployments \
  -f state=approved \
  -F environment_ids="[$STAGING_ENV_ID]" \
  -f comment='self-approval by sole maintainer'

# Approve production deployment  
gh api -X POST repos/veyorokon/visureel-api/actions/runs/$RUN_ID/pending_deployments \
  -f state=approved \
  -F environment_ids="[$PROD_ENV_ID]" \
  -f comment='self-approval by sole maintainer'
```

## Notes

- Keep production gated even as sole maintainer - audit trail remains clear
- All approvals are logged and visible in GitHub Actions deployment history
- When adding team members, update environment reviewers and ADR-0003
- Production has 30-second wait timer for additional safety

## Emergency Procedures

- Disable deployment gates: `gh variable set DEPLOY_ENABLED_PROD --body "false"`
- Direct ECS management: Use AWS console or CLI to manage services directly
- Rotate credentials: Update GitHub secrets if AWS keys are compromised