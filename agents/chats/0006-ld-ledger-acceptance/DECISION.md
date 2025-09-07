---
id: 0006
area: ld
slug: ledger-acceptance
status: approved
closed: 2025-09-07T14:30:00Z
---

# DECISION: 0006 [ld] ledger-acceptance

## Status
✅ APPROVED — Core ledger invariants validated; scope complete.

## Decision
- Adopt prev_hash-chained event hashing: `this_hash = H(prev_hash_bytes || canonical_json)`; first event uses empty prefix.
- Standardize event payload schema: `event_type` and `plan_id` (stable key), with budget events `budget.reserved` and `budget.settled`.
- Validate via acceptance/property tests on SQLite and docs `-W` gate; defer PostgreSQL-only concurrency tests to a DX infra chat.

## Rationale
- Aligns with invariants (hash chain continuity, reserve→settle accounting) and docs-as-contracts.
- Keeps scope minimally sufficient (no scheduler/leases; tenancy out-of-scope).

## Outcomes
- LedgerWriter implements transactional sequencing and reserve→settle.
- Hash continuity and budget invariants proven in tests.
- Documentation updated with correct formula and worked example; docs build clean.

## Follow-ups
- Open DX chat to configure PostgreSQL roles and enable compose-backed concurrency tests.

