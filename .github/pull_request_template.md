# Pull Request

## Summary
Brief description of the changes made.

## Links
- **Related Issue:** Fixes #
- **ADR (if applicable):** 

## Type of Change
- [ ] Bug fix (non-breaking change)
- [ ] New feature (non-breaking change)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation only changes
- [ ] CI/CD change (governed by ADR-0003)

## CI/CD Changes (if applicable)
*Complete this section only if "CI/CD change" is checked above*

### Governance Checklist (must all pass)
- [ ] Workflows updated AND docs build passes in CI
- [ ] Docs updated (guides/ci-cd.md or ADR-0003 Status) if behavior changed
- [ ] Deploy remains gated unless enabling CD intentionally
- [ ] If enabling CD:
  - [ ] GitHub Environment exists (development/staging/production)
  - [ ] Reviewers/approvals configured
  - [ ] Required secrets present (documented)
- [ ] Rollout/backout steps documented in the PR

### Environment Flags
- [ ] Any environment flags toggled? (`DEPLOY_ENABLED_DEV`, `DEPLOY_ENABLED_STAGING`, `DEPLOY_ENABLED_PROD`)
- [ ] Any Terraform/ECS identifiers referenced?

## Testing
- [ ] Tests pass locally
- [ ] Documentation builds successfully
- [ ] Changes tested in appropriate environment

## Documentation
- [ ] Code changes include relevant documentation updates
- [ ] Generated documentation refreshed (if applicable)
- [ ] ADR updated (if architectural change)