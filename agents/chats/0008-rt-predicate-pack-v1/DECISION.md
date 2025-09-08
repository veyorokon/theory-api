# DECISION

**Status:** Approved/Closed
**Date:** 2025-09-08
**Decided by:** Architect

## Decision
Ship Predicate Pack v1 with four predicates (`artifact.exists@1`, `series.has_new@1`, `json.schema_ok@1`, `tests.pass@1`) that are deterministic, hermetic, and aligned to facet‑root WorldPath canonicalization and storage/registry contracts.

## Implementation Notes
- Canonicalization at ingress: lowercase, collapse `//`, percent‑decode once, Unicode NFC, reject encoded slashes (`%2F`), forbid `.`/`..`, facet‑root only (`/artifacts/**`, `/streams/**`).
- `artifact.exists@1`: uses storage service to stat; returns False on missing/errors.
- `series.has_new@1`: compares Truth watermark (safe fallback to 0 if streams not wired yet).
- `json.schema_ok@1`: loads JSON from artifact via storage; resolves schema from generated registry or file; validates via `jsonschema`; returns bool only.
- `tests.pass@1`: subprocess `pytest -q --disable-warnings` with timeout; sandboxed to `/artifacts/<plan>/tests/`; returns bool only.
- Registry export lists all four under `_generated/registry/`.

## Outcomes
- Unit + acceptance tests pass; docs export succeeds.
- Hermetic predicates with robust path safety; no network or project‑wide test recursions.

## Lessons Learned
- Keep predicates pure and fast; enforce canonicalization at every ingress.
- Sandbox execution paths explicitly to avoid accidental scope.

