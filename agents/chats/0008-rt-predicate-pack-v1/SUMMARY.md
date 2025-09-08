# SUMMARY

## Scope
Predicate Pack v1: implement `artifact.exists@1`, `series.has_new@1`, `json.schema_ok@1`, and `tests.pass@1` with strict facet‑root canonicalization, storage/registry alignment, and hermetic testing.

## Conversation
- 001-to-engineer (architect): Initial spec for four predicates + registry export and tests.
- 002-to-architect (engineer): Reported implementation progress and alignment.
- 003-to-engineer (architect): Micro-tweaks (encoded slash check, sandbox tightening, test settings) and smoke request.
- 004-to-architect (engineer): Confirmed fixes; unit/acceptance/docs all passing.

## Key Changes
- Ingress canonicalization: lowercase, NFC, percent-decode once, collapse `//`, reject `%2F`, forbid `.`/`..`, facet-root only.
- `artifact.exists@1`: storage service stat; False on missing/errors.
- `series.has_new@1`: Truth watermark accessor with safe fallback until streams are wired.
- `json.schema_ok@1`: artifact JSON via storage; schema via generated registry or file; `jsonschema` validation.
- `tests.pass@1`: hermetic subprocess `pytest` under `/artifacts/<plan>/tests/` only; returns boolean.
- Registry: predicates appear under `_generated/registry/` via docs export.

## Technical Details
### Architecture
- Predicates remain pure, deterministic, and fast; no network or project-wide test recursion.
- Path safety is enforced consistently across predicates.

### Implementation
- Tight sandbox for `tests.pass`; robust error handling returning False.
- Storage/series/jsonschema accessors encapsulate side effects; tests rely on mocks and markers.

## Validation
- Unit: `make test-unit -k predicates` green.
- Acceptance: `make test-acceptance -k predicates` green.
- Docs: `make docs` green; registry updated.

## Risks & Mitigations
- Minimal; all error paths return False; sandbox prevents accidental scope.

## Follow-up Items
- [ ] Wire real streams Truth path in 0014 to replace the series stub fallback.

## PR Links
- PR: TBD (engineer to open to `dev`).

