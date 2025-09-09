# SUMMARY

## Scope
Modal adapter + unified `run_processor` CLI with attachments-to-artifacts flow; add `artifact.jmespath_ok@1`; standardize new events on `kind` + `ts`; remove `hello_llm`; add small shims to prevent abstraction bleed.

## Conversation
- 001-to-architect (architect): Kicked off CLI, attachments, predicates, events, docs removal.
- 002-to-architect (engineer): Implementation plan (CLI, predicate, providers, events, processor registry, docs).
- 004-to-engineer (architect): Refactor deltas — providers→adapters, ArtifactStore, RuntimeAdapter, env_fingerprint, exporter hook.
- 005/006-to-architect (engineer): Reported refactor + final cleanup done; docs/tests green.

### Pivotal Chats (late phase)
- 024-to-twin (architect): Status/gaps vs canonical spec; proposed unification plan and streaming stance.
- 025-to-architect (twin): Alignment brief to close 0021 (canonical outputs, streaming outline, docs, tests).
- 026-to-engineer (architect): Code-aware deltas for canonical outputs, CLI plumbing, save flags.
- 027-to-engineer (architect): Review of current code; precise changes to finish 0021.
- 028/030-to-architect (engineer): Claimed/confirmed C-01..C-04 implemented; canonical envelope present; CLI flags added.
- 031-to-engineer (architect): Tiny delta — ensure env_fingerprint fallback in CLI receipts.
- 032-to-engineer (architect): Docs alignment plan (use case, events, registry/adapters, core link, index pointers).
- 033-to-architect (twin): Modal wrapper pattern (warm/run), snapshots, adapter parity, canonical outputs; ready for diffs.
- 034-to-architect (architect): Acknowledged twin plan; omit region in env_fingerprint; risks/tests noted.
- 035-to-engineer (architect): Final deltas — Modal wrapper parity, post-transfer canonical walk, env_fingerprint fields, tests, docs tie‑in.

## Key Changes
- CLI: `run_processor` with `--attach` materialization and `$attach`→`$artifact` rewrites.
- Adapters: runtime placement at `apps/core/adapters/{base,local_adapter,modal_adapter,mock_adapter}.py`.
- Predicates: `artifact.jmespath_ok@1` (truthy|equals) added (`jmespath>=1`).
- Events: new code uses `kind` + UTC Z `ts`; JCS + BLAKE3 continuity for new paths.
- Shims: `ArtifactStore` and `env_fingerprint` util; `RuntimeAdapter` ABC.
- Docs: exporter renders processor registry fields; `hello_llm` removed from code/docs; examples updated to `run_processor`.

## Technical Details
### Architecture
- Adapters execute containerized processors; SDKs live inside images; predicates verify.
- WorldPaths are facet-root; write-prefix ends with `/`; attachments stored under `/artifacts/inputs/<cid>/...`.

### Implementation
- Determinism receipts integrated via prior 0009; first Modal smoke targets `llm/litellm@1` (CPU-only).
- Processor registry fields include `image.oci`, `runtime.*`, `adapter.modal.*`, `secrets`, `outputs`.

## Validation
- Unit lane green; CLI demos for local/mock; docs drift + build `-W` clean; processor registry rendered.
- ✅ Full CI/CD validation: unit (52), acceptance (23), property (8), docs, linting - all tests pass.

## Canonical Outputs (0021 completion)
- Adapters (local, mock) now produce a canonical envelope:
  - `status`, `execution_id`, `outputs: [{path,cid,size_bytes,mime}]` (lexicographically sorted), `index_path`, `meta{image_digest, env_fingerprint, duration_ms, io_bytes}`.
  - Index artifact written to `/artifacts/execution/<execution_id>/outputs.json` with JCS-style JSON (stable bytes).
  - Duplicate-target rejection enforced after WorldPath canonicalization.
- CLI updates:
  - Passes `execution_id` into adapters; derives determinism `output_cids` from canonical `outputs`.
  - Additive settle fields supported: `outputs_index`, `outputs_count` (keeps tests green).
  - DX flags: `--save-dir` (mirror world paths locally), `--save-first` (download first output).
- Modal parity: adapter scaffold exists behind `MODAL_ENABLED`; full canonicalization will be wired in 0022 (or earlier with credentials and `image.oci`).

## Outstanding Nits
- ✅ Determinism `env_fingerprint`: CLI fallback implemented (C‑05 complete). Determinism receipts now properly capture `env_fingerprint` from adapter meta.

## Risks & Mitigations
- Minimal; remaining legacy `litellm_provider` will be removed in the next slice with a CI guard.

## Follow-up Items
- [ ] Remove `apps/core/providers/litellm_provider.py` and drop `litellm` from Django `requirements.txt`; add CI guard.
- [ ] Modal adapter: wire post-exec canonicalization (parity with local/mock) behind `MODAL_ENABLED`.
- ✅ CLI: apply `env_fingerprint` fallback (C‑05) to ensure receipts always include fingerprint. **COMPLETE**

## PR Links
- PR: (engineer to link the 0021 branch PR to `dev`).
