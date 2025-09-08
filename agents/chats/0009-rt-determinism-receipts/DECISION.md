# DECISION

**Status:** Approved/Closed
**Date:** 2025-09-08
**Decided by:** Architect

## Decision
Land determinism receipts: write `/artifacts/execution/<id>/determinism.json` on successful settle and include a pointer (`determinism_uri`) in the settled event payload. Budget math clears reserves atomically; memo hits are explicit events.

## Implementation Notes
- Storage: Added a tiny `upload_bytes` shim on `storage_service`; receipts are uploaded via adapters.
- Ledger: Used `LedgerWriter().append_event(plan, payload)` with `event_type` and pointer to receipt.
- Models: No new fields on `Execution`; settlement helpers update `Plan` and emit events.
- Bytes: `{"seed":int,"memo_key":str,"env_fingerprint":str,"output_cids":[str,...]}` serialized with compact separators.

## Outcomes
- Unit + acceptance tests pass; docs build clean.
- Every success settles with a deterministic receipt and a ledger event pointer for audit.

## Lessons Learned
- Keep audit bytes simple and stable; decouple from code execution.
- Prefer helpers + events over model field churn for iterative features.

