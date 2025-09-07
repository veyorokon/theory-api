# SUMMARY

## Scope
Proved core ledger invariants: reserve→settle atomicity, per‑plan sequence monotonicity, and hash‑chain continuity, with documentation updated and PostgreSQL‑only concurrency tests deferred to a DX infra follow‑up.

## Conversation
- 009-to-architect (engineer): Reported Step B completion; implemented LedgerWriter, fixed pytest infra; 30/31 tests passing (1 skip expected).
- 010-to-engineer (architect): Accepted Step B with nits — include prev_hash in hash, standardize payload fields, add continuity test and doc updates.
- 012-to-engineer (architect): Confirmed docs config tweak request; asked for full smoke; set owner to engineer.
- 013-to-engineer (architect): Removed premature DECISION/SUMMARY; restated Makefile-based smoke and closure protocol.
- 014-to-architect (engineer): Confirmed Sphinx already on backend; identified docs warning (duplicate heading); PG tests blocked by role setup.
- 015-to-engineer (architect): Accepted impl; requested docs heading rename (C-14); deferred PG tests to DX chat.
- 016-to-architect (engineer): Applied C-14; docs -W clean; ready to close.
- 017-to-engineer (architect): Closed chat; added decision and summary; marked state closed.

## Key Changes
- Implemented prev_hash‑chained event hashing (`this_hash = H(prev_hash_bytes || canonical_json)`; empty prefix for first event)
- Standardized payload schema (`event_type`, `plan_id`; `budget.reserved`/`budget.settled`)
- Added transactional LedgerWriter operations (`append_event`, `reserve_execution`, `settle_execution` with row locks)
- Added acceptance + property tests (including a seq=2 hash‑continuity assertion)
- Updated `docs/source/concepts/ledger-events.md`; docs build passes with `-W`

## Technical Details
### Architecture
- Events as truth with BLAKE3 hash chain; per‑plan monotonic `seq` and `UNIQUE(plan, seq)` constraint (conceptual)
- Reserve→settle accounting preserved; first event uses empty prefix in hash chain

### Implementation
- `event_hash(payload, prev_hash)`: canonical JSON bytes prefixed by `prev_hash` bytes
- `LedgerWriter`: `select_for_update` for budget rows; atomic append/sequence; standardized payload fields
- SQLite used for core validation; PostgreSQL concurrency tests deferred

## Validation
- Tests: acceptance (ledger_acceptance on SQLite), property (budget never negative), hash‑continuity
- Docs: `make docs` passes with zero warnings
- CI guidance: Makefile targets are canonical for gates

## Risks & Mitigations
- Hash incompatibility with earlier payload‑only formula — acceptable now (pre‑prod), documented in decision
- Payload field rename may affect consumers — mitigated by aligning docs and tests

## Follow-up Items
- [ ] DX: Configure PostgreSQL roles and run PG‑only concurrency tests
- [ ] Confirm any downstream consumers updated for `event_type`/`plan_id`

## PR Links
- PR: TBD
- Issue: TBD
