# SUMMARY

## Scope
Introduce a leases façade in Core to canonicalize WorldPaths, define overlap semantics (plan‑scoped, segment‑aware), and expose a no‑op `LeaseManager` API for future admission without changing runtime behavior.

## Conversation
- 001-to-engineer (architect): Scaffold façade intent (flag‑gated no‑op, overlap helper, tests).
- 002-to-engineer (architect): Full spec: helpers, selector types, overlap matrix, façade API, tests, docs, SMOKE.
- 003-to-engineer (architect): Acceptance details and edge cases.
- 004-to-engineer (architect): Stubs + tests scaffold added; proceed to validate.

## Key Changes
- Added `apps.core.leases` package with helpers and `LeaseManager` façade (no‑op).
- Added segment‑aware, plan‑scoped overlap checks (`paths_overlap`, `selectors_overlap`, `any_overlap`).
- Added unit tests scaffold for canonicalization and overlap matrix.
- Updated Core docs with a short “Leases (Façade)” section.

## Technical Details
### Architecture
- Leases live in Core (admission/scheduling concern), not Storage; backed by TruthStore later.
- Facade is flag‑gated and isolated; no runtime enforcement yet.

### Implementation
- Canonical grammar: lowercase, '/world/' prefix, single slashes, no trailing slash.
- Overlap: equal or ancestor/descendant within same (tenant, plan); similar names (foo vs foobar) do not overlap.
- LeaseManager: `acquire` returns canonicalized write_set; `release` no‑ops.

## Validation
- Local smoke confirms canonicalization, parse, overlap logic, and façade behavior.
- Tests scaffold present: run `make test-unit` and `pytest -k leases` locally.
- Docs: `make docs` after changes.

## Risks & Mitigations
- None; façade is isolated and disabled by default.

## Follow-up Items
- [ ] Future: add persistence and real enforcement; integrate into admission when ready.

## PR Links
- PR: TBD (engineer to open against `dev`).

