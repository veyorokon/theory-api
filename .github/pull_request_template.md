## Summary
<!-- One-liner: smallest correct change -->

## Traceability
- Issue: <!-- #123 or link (required) -->
- ADR: <!-- ADR-XXXX or n/a (explain why) -->

## Docs (required)
- [ ] Guides updated
- [ ] Concepts updated
- [ ] API/autodoc updated (models/services)
- Touched files:
  - `docs/source/...`

## Risk & Rollout
- Risk: <!-- low/med/high + why -->
- Backout: <!-- exact steps -->

## Local Verification
```bash
cd code && python manage.py docs_export --out ../docs/_generated --erd --api --schemas
sphinx-build -n -W -b html docs/source docs/_build/html
sphinx-build -b linkcheck docs/source docs/_build/linkcheck
```

## Screenshots / Artifacts
<!-- optional -->

## Deployment (Sole Maintainer)
- [ ] If this PR deploys to staging/production, I will self-approve pending deployments per ADR-0003 runbook