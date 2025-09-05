# CI/CD Operations Guide

This guide covers operational procedures for the CI/CD pipeline established by [ADR-0003](../adr/ADR-0003-branch-strategy-cicd).

## Pipeline Overview

The CI/CD pipeline follows a three-tier deployment strategy:

```{mermaid}
graph LR
    A[Feature Branch] --> B[dev branch]
    B --> C[staging branch] 
    C --> D[main branch]
    
    B -.-> E[Dev Environment]
    C -.-> F[Staging Environment] 
    D -.-> G[Production Environment]
    
    style E fill:#e1f5fe
    style F fill:#fff3e0
    style G fill:#e8f5e8
```

## Deployment Gates

All deployments are controlled by environment variables and GitHub Environment protection:

- **CI always runs:** Tests, linting, and docs build on all PRs and merges
- **CD is gated by:**
  - Repository variables: `DEPLOY_ENABLED_DEV`, `DEPLOY_ENABLED_STAGING`, `DEPLOY_ENABLED_PROD`
  - GitHub Environments with required reviewers (staging/production)
  - AWS credentials and ECS infrastructure availability

## Environment Management

### Enable Deployment for an Environment

1. **Create GitHub Environment:**
   ```bash
   # Via GitHub CLI (if available)
   gh api repos/veyorokon/theory-api/environments/development -X PUT
   
   # Or via web interface: Settings → Environments → New environment
   ```

2. **Configure Environment Protection:**
   - **Development:** No required reviewers (rapid iteration)
   - **Staging:** Optional reviewers for integration testing
   - **Production:** Required reviewers (1+ team members)

3. **Add Required Secrets at Environment Scope:**
   ```
   AWS_ACCESS_KEY_ID
   AWS_SECRET_ACCESS_KEY
   ```

4. **Enable Deployment Flag:**
   ```bash
   # Via GitHub CLI
   gh variable set DEPLOY_ENABLED_DEV --body "true"
   gh variable set DEPLOY_ENABLED_STAGING --body "true"  
   gh variable set DEPLOY_ENABLED_PROD --body "true"
   
   # Or via web interface: Settings → Secrets and variables → Actions
   ```

5. **Verify ECS Infrastructure:**
   Ensure these resources exist via Terraform:
   ```
   theory-dev-cluster / theory-api-dev
   theory-staging-cluster / theory-api-staging  
   theory-prod-cluster / theory-api-prod
   ```

6. **Test First Deployment:**
   - Merge to target branch
   - Monitor Actions tab for deployment logs
   - If failure: disable flag, fix issues, re-enable

### Disable Deployment (Backout)

1. **Immediate Disable:**
   ```bash
   gh variable set DEPLOY_ENABLED_DEV --body "false"
   gh variable set DEPLOY_ENABLED_STAGING --body "false" 
   gh variable set DEPLOY_ENABLED_PROD --body "false"
   ```

2. **No Code Rollback Required:**
   - Deployment gates are workflow-level
   - Existing deployments remain running
   - New merges will skip deployment steps

3. **Emergency Procedures:**
   - Rotate AWS credentials if compromised
   - Temporarily disable Environment protection if needed
   - Use ECS console for direct service management

## Making CI/CD Changes

All CI/CD modifications follow the governance process established by ADR-0003:

### 1. Open Governed Issue

Use the **CI/CD Change** issue template with required fields:
- Summary of change and rationale
- Scope checklist (workflows, environments, secrets, docs)
- Acceptance criteria with concrete outcomes
- Rollout and backout procedures
- Links to ADR-0003

### 2. Create Pull Request

Use the standard PR template with CI/CD governance checklist:
- [ ] Workflows updated AND docs build passes
- [ ] Documentation updated if behavior changed
- [ ] Deployment gates remain intact
- [ ] GitHub Environments configured (if enabling CD)
- [ ] Rollout/backout documented

### 3. Review and Merge

- All CI/CD PRs require review per branch protection
- Docs build must pass (enforced by required status checks)
- Agent or reviewers verify governance checklist completion

## Troubleshooting

### Common Issues

**Deployment Skipped Despite Flag Enabled:**
- Check GitHub Environment exists and has required secrets
- Verify AWS credentials have ECS permissions
- Confirm ECS cluster and service names match workflow

**Build Failures:**
- Django tests failing: Check database connectivity in Actions
- Docs build failing: Run `make -C docs html` locally first
- Docker build failing: Verify Dockerfile and dependencies

**Permission Errors:**
- AWS credentials: Verify IAM permissions for ECR/ECS
- GitHub: Ensure Actions have required repository permissions
- Secrets: Check environment-scoped vs repository-scoped secrets

### Monitoring

- **Actions Tab:** Real-time pipeline status and logs
- **ECS Console:** Service health and deployment status  
- **CloudWatch:** Application logs and metrics
- **GitHub Environments:** Deployment history and approvals

## GitHub Pages (Documentation Publishing)

Our documentation is automatically built and published to GitHub Pages on every merge to `main`.

### Troubleshooting Pages Deployment

**404 Error on Deploy (most common):**
If the workflow build succeeds but deploy fails with "404" or "Not Found":

1. **Disable and re-enable Pages:**
   - Go to Settings → Pages in the repository
   - Click "Disable" if Pages is currently enabled
   - Click "Enable" and set Source = "GitHub Actions"
   - Save settings

2. **Verify workflow configuration:**
   ```bash
   # Our workflow uses the canonical pattern
   # configure-pages → upload-pages-artifact → deploy-pages
   # with environment name exactly "github-pages"
   ```

3. **Manual workflow trigger:**
   ```bash
   # Test deployment after fixing Pages settings
   gh workflow run docs.yml
   gh run watch --exit-status
   ```

**Common Issues:**
- Environment name must be `github-pages` (not "pages" or "Docs")
- Upload path points to built site: `docs/_build/html`
- Permissions include `pages: write` and `id-token: write`
- Pages source is "GitHub Actions," not branch/folder

## Security Considerations

- **Secrets Rotation:** AWS credentials should be rotated regularly
- **Environment Isolation:** Each environment uses separate AWS resources
- **Branch Protection:** Production deploys require human review
- **Audit Trail:** All changes tracked through Issues → PRs → ADR updates

See [ADR-0003](../adr/ADR-0003-branch-strategy-cicd) for architectural decisions and [Getting Started](getting-started) for development workflow.