# DECISION

**Status:** Approved/Closed
**Date:** 2025-09-07
**Decided by:** Architect

## Decision
Adopt a CI guard that enforces “docs as contracts”: regenerate generated docs, fail on drift under `docs/_generated/**`, then build Sphinx with `-W`.

## Implementation Notes
- Workflow `.github/workflows/docs.yml` runs on PR to dev/staging/main and push to main.
- Steps: pip install deps → `python manage.py docs_export --erd --api --schemas` → `git diff --exit-code -- docs/_generated` → `make -C docs -W html`.
- Uploads the built HTML as an artifact for inspection.

## Outcomes
- Local: `make docs` runs export + drift check + Sphinx build.
- CI: PRs fail on drift with a clear message; otherwise Sphinx builds with warnings treated as errors.

## Lessons Learned
- Locking docs early prevents drift as code evolves.
- Using Makefile targets keeps local and CI workflows aligned.

