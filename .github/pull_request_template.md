## Summary
<!-- One-liner: smallest correct change -->

## Traceability
- Chat: <!-- 0005-dx-gh-sync (required for agent-coordinated work, or n/a) -->
- Issue: <!-- #123 or link (required) -->
- ADR: <!-- ADR-XXXX or n/a (explain why) -->

## Agent Coordination (if applicable)
- [ ] Chat meta.yaml updated with outputs and acceptance criteria
- [ ] Architect approved in chat thread
- [ ] All acceptance criteria from meta.yaml verified

## Validation
- [ ] Meta schema: `python theory_api/agents/validate_chat_meta.py $(find theory_api/agents/chats -name meta.yaml)`
- [ ] Message validation: `python theory_api/agents/validate_chat_msgs.py $(find theory_api/agents/chats -maxdepth 1 -type d)`
- [ ] PR title matches pattern: `XXXX [area] slug` (for agent-coordinated work)

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