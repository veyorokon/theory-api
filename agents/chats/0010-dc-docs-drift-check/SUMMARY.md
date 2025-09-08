# SUMMARY

## Scope
Enforce “docs as contracts” via CI: export generated docs, fail on drift under `docs/_generated/**`, then build Sphinx with `-W`.

## Conversation
- 001-to-engineer (architect): Spec for docs workflow and Make targets.
- 002-to-architect (engineer): Confirmed workflow present and green; make docs passes locally; CI fails on drift.
- 003-to-engineer (architect): Accepted and closed.

## Key Changes
- Added `.github/workflows/docs.yml` (CI: export → drift check → Sphinx -W).
- Makefile targets (`docs-export`, `docs-drift-check`, `docs`) available for local parity.

## Technical Details
### Architecture
- CI-only guard to keep generated docs and manual docs in lockstep.

### Implementation
- Python 3.11 setup, pip install requirements, export docs, drift check, Sphinx -W build, HTML artifact upload.

## Validation
- Local: `make docs` green.
- CI: Editing a generated file without export causes failure.

## Risks & Mitigations
- None; isolated to CI.

## Follow-up Items
- [ ] Optional: Link docs build badge in README.

## PR Links
- PR: TBD (engineer to open to `dev`).

