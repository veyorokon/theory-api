# DECISION

**Status:** Approved/Closed
**Date:** 2025-09-09
**Decided by:** Architect

## Decision
Deliver Modal adapter + unified `run_processor` CLI with attachments-to-artifacts flow, add `artifact.jmespath_ok@1`, standardize new events on `kind` + UTC Z `ts`, and remove `hello_llm`. Establish adapters as runtime placement (local|mock|modal), keep SDKs inside containerized processors, and add small shims (ArtifactStore, RuntimeAdapter ABC, env_fingerprint) to prevent abstraction bleed.

## Implementation Notes
- CLI: `run_processor` supports `--ref/--adapter/--plan/--write-prefix/--inputs-json [--adapter-opts-json] [--attach ...] [--json] [--stream]` with `$attach` → `$artifact` rewrites.
- Adapters: providers → adapters at `apps/core/adapters/{base,local_adapter,modal_adapter,mock_adapter}.py`; local runs containers.
- Predicates: `artifact.jmespath_ok@1` (truthy|equals) added with `jmespath>=1`.
- Events: new code uses top-level `kind` + `ts`; JCS+ BLAKE3 continuity verified for new paths.
- Shims: `ArtifactStore` (facet-root → storage), `RuntimeAdapter` ABC, `env_fingerprint` util.
- Docs: exporter renders processor registry fields; examples updated to `run_processor`; `hello_llm` docs/tests removed.

## Outcomes
- Single mental model: adapters execute processors; processors package SDKs; predicates verify artifacts/events; receipts record determinism.
- Docs and CI remain green; drift reduced via exporter rendering.

## Lessons Learned
- Naming matters: “providers” conflated concerns; “adapters” clarifies placement.
- Keep SDKs in images to avoid Django drift and ensure receipts/fingerprints are honest.

