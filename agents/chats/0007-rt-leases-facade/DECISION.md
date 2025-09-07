# DECISION

**Status:** Approved/Closed
**Date:** 2025-09-07
**Decided by:** Architect

## Decision
Adopt a minimal, flag‑gated leases façade in Core: canonical WorldPath handling, segment‑aware overlap checks within a plan, and a no‑op `LeaseManager` API (`acquire/release`). No runtime enforcement yet.

## Implementation Notes
- Module: `apps.core.leases` with helpers (`canonicalize_path`, `parse_world_path`, `canonicalize_selector`) and overlap (`paths_overlap`, `selectors_overlap`, `any_overlap`).
- Façade: `LeaseManager(enabled=False)` returns canonicalized `Lease` on `acquire` and no‑ops on `release`.
- Settings: `LEASES_ENABLED` flag (env‑driven) exists; not used for runtime enforcement yet.
- Docs: Core app updated with a short “Leases (Façade)” section.

## Outcomes
- Deterministic path grammar + overlap semantics established for future admission/leases.
- Test scaffold added and smoke verified; no behavior changes to runtime.

## Lessons Learned
- Establishing canonical path and overlap contracts early reduces risk when adding real leases.
- Keep façade isolated and flag‑gated to avoid behavioral drift.

