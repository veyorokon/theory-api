# SUMMARY

## Scope
Modal adapter + unified `run_processor` CLI with attachments-to-artifacts flow; add `artifact.jmespath_ok@1`; standardize new events on `kind` + `ts`; remove `hello_llm`; add small shims to prevent abstraction bleed.

## Conversation
- 001-to-architect (architect): Kicked off CLI, attachments, predicates, events, docs removal.
- 002-to-architect (engineer): Implementation plan (CLI, predicate, providers, events, processor registry, docs).
- 004-to-engineer (architect): Refactor deltas — providers→adapters, ArtifactStore, RuntimeAdapter, env_fingerprint, exporter hook.
- 005/006-to-architect (engineer): Reported refactor + final cleanup done; docs/tests green.

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

## Risks & Mitigations
- Minimal; remaining legacy `litellm_provider` will be removed in the next slice with a CI guard.

## Follow-up Items
- [ ] Remove `apps/core/providers/litellm_provider.py` and drop `litellm` from Django `requirements.txt`; add CI guard.

## PR Links
- PR: (engineer to link the 0021 branch PR to `dev`).

