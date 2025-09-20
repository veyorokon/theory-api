
# ENGINEER — North Star & Operating Manual (v4)

## 0) Identity & Prime Directives

* **Role:** Senior engineer for a Modal-first Django backend that executes pinned processors deterministically.
* **Prime directives:**

  1. **Smallest correct change** (docs are contracts).
  2. **Honor invariants** (registry pinning, receipts, world paths, adapter parity).
  3. **Two modes only:** `mock` and `real` (no “smoke” mode).
  4. **No cross-layer leaks:** processors self-contained; Django orchestrates.
  5. **One public surface:** adapters return canonical envelopes; providers are callables.

## 1) Architecture Snapshot

* **Processors (containers):** thin `main.py` + `provider.py` + `requirements.txt` (SDKs live here).
* **Adapters (Django):** `LocalAdapter`, `ModalAdapter` — same `invoke(*, …)` contract → canonical envelope.
* **Shared libs:** `libs/runtime_common/*` — args parsing, inputs normalization, hashing, receipts, outputs index, logging, mode resolution.
* **Registry:** `code/apps/core/registry/processors/*.yaml` pinned to **repo-scoped** GHCR images
  e.g., `ghcr.io/<owner>/<repo>/<processor>@sha256:<digest>`.
* **Modes:**

  * `mock`: no external calls; produces deterministic mock outputs.
  * `real`: uses real provider SDKs/secrets.

## 2) Public Contracts (MUST NOT DRIFT)

### Adapters

```py
# Keyword-only; returns canonical JSON envelope (success|error).
LocalAdapter.invoke(*, plan_id, processor_ref, write_prefix, inputs_json, mode, execution_id, ...) -> dict
ModalAdapter.invoke(*, ...) -> dict

# Success envelope (minimal):
{
  "status": "success",
  "execution_id": "...",
  "outputs": [{"path": "world://..."}],          # paths are world/canonical, no bodies
  "index_path": "world://.../outputs.json",      # sorted, compact writer
  "meta": {"env_fingerprint": "..."}             # deterministic summary
}

# Error envelope (canonical):
{
  "status": "error",
  "execution_id": "...",
  "error": {"code": "ERR_*", "message": "safe text"},
  "meta": {"env_fingerprint": "..."}
}
```

### Provider interface (uniform)

```py
def make_runner(config: dict) -> Callable[[dict], ProcessorResult]:
    ...
```

* **Runner inputs:** normalized `{"schema":"v1","model":<optional>,"params":{...},"files":{...},"mode":"mock|real"}`.
* **ProcessorResult:** `{ outputs: [OutputItem], processor_info: str, usage: dict, extra: dict }`.

  * **Note:** `processor_info` is a **string** (human-readable), not a dict.

## 3) Modes (single source of truth)

* `libs/runtime_common/mode.py`

  * `resolve_mode(inputs) -> ResolvedMode("mock" | "real")`
  * **CI guardrail:** if `CI=true` and `mode == "real"`, raise `ERR_CI_SAFETY` (command exits non-zero).
* No environment heuristics (`LLM_PROVIDER=mock`, etc.) — **explicit only**.

## 4) Logging (structured & safe)

* Use `apps/core/logging.py` helpers. JSON to stdout by default.
* Bind once per execution: `trace_id=execution_id`, plus `adapter`, `processor_ref`, `mode`.
* Redaction filter on secrets; log hashes/sizes, never payload bodies.

## 5) CLI: daily tasks

```bash
# Run locally (mock)
cd code
python manage.py run_processor \
  --ref llm/litellm@1 \
  --adapter local \
  --mode mock \
  --write-prefix "/artifacts/outputs/demo/{execution_id}/" \
  --inputs-json '{"schema":"v1","params":{"messages":[{"role":"user","content":"hi"}]}}' \
  --json

# Run on Modal (dev) (mock)
MODAL_ENV=dev python manage.py run_processor \
  --ref llm/litellm@1 --adapter modal --mode mock \
  --write-prefix "/artifacts/outputs/demo/{execution_id}/" \
  --inputs-json '{"schema":"v1","params":{"messages":[...]}}' --json

# Scaffold a new processor (repo-scoped GHCR naming baked in)
python manage.py scaffold_processor --ref vision/replicate@1
```

## 6) CI/CD: order of operations (dev environment)

1. **Acceptance & property tests** (Docker stack up) — local & CI parity.
2. **Build & Pin** (multi-arch `linux/amd64,linux/arm64`): builds → pushes → bot PR updates digests.
3. **Modal Deploy (dev)**: deploy functions (with `serialized=True`) → **mock** validation run.
4. (Optional) **Promotion** to staging/main after dev is green.

## 7) Secrets (uniform & synced)

* Processors require secret **names**; adapters don’t pass values.
* CI step syncs GitHub → Modal if missing (`OPENAI_API_KEY`, `REPLICATE_API_TOKEN`, …).
* Modal app reads secret **names**; Modal provides values at runtime.

## 8) Troubleshooting checklist

* **Image pull fails / manifest unknown:** registry YAML digest stale → rerun Build & Pin (or accept bot PR).
* **ARM64 pull fails:** ensure multi-arch buildx producing manifest list; local dev can `--build` for native.
* **Receipt tests fail:** confirm fingerprint format & pinned image strings match expectations.
* **Mode confusion:** inputs must include `"mode":"mock"` for tests; CI guardrail blocks `real`.
* **Modal “missing secret” after sync:** verify same Modal **env** as deploy; function redeployed after app changes; function decorated with `serialized=True`.

## 9) Examples (copy/paste)

### LLM provider (`apps/core/processors/llm_litellm/provider.py`)

```py
from dataclasses import dataclass
from typing import Callable, Dict, Any, List, Optional

@dataclass
class OutputItem:
    relpath: str
    bytes_: bytes
    meta: Optional[Dict[str, str]] = None

@dataclass
class ProcessorResult:
    outputs: List[OutputItem]
    processor_info: str
    usage: Dict[str, float]
    extra: Dict[str, str]

def make_runner(config: Dict[str, Any]) -> Callable[[Dict[str, Any]], ProcessorResult]:
    import litellm

    def _runner(inputs: Dict[str, Any]) -> ProcessorResult:
        mode = inputs.get("mode", "mock")
        msgs = inputs.get("params", {}).get("messages", [])
        if mode == "mock":
            text = "MOCK: " + (msgs[0]["content"] if msgs else "")
            payload = {"choices":[{"message":{"role":"assistant","content":text}}]}
            body = (  # deterministic, small
                ('{"model":"mock","object":"chat.completion","choices":[{"message":{"role":"assistant","content":'
                + repr(text) + '}}]}').encode("utf-8")
            )
        else:
            # Use completion or chat path per installed LiteLLM; normalize to dict
            resp = getattr(litellm, "completion", None)
            if callable(resp):
                r = litellm.completion(model=inputs.get("model","gpt-4o-mini"), messages=msgs)
                payload = r.model_dump() if hasattr(r, "model_dump") else r  # normalize
            else:
                r = litellm.chat.completions.create(model=inputs.get("model","gpt-4o-mini"), messages=msgs)
                payload = r.model_dump() if hasattr(r, "model_dump") else r

            body = __import__("json").dumps(payload, separators=(",",":")).encode("utf-8")

        out = OutputItem(relpath="outputs/response.json", bytes_=body)
        return ProcessorResult(outputs=[out], processor_info="llm_litellm:v1", usage={}, extra={})

    return _runner
```

### Replicate provider (uniform callable)

```py
def make_runner(config):
    import replicate, json, urllib.request, pathlib

    def _runner(inputs):
        mode = inputs.get("mode", "mock")
        if mode == "mock":
            body = b'{"result":["https://example.invalid/mock.webp"]}'
            return ProcessorResult(outputs=[OutputItem("outputs/response.json", body)], processor_info="replicate_generic:v1", usage={}, extra={})

        model = inputs.get("model", "black-forest-labs/flux-schnell")
        params = inputs.get("params", {})
        client = replicate.Client(api_token=None)  # Modal injects secrets
        result = client.run(f"{model}", input=params)
        # Serialize + (optional) asset download already handled in processor main
        body = json.dumps({"result": result}, separators=(",",":")).encode("utf-8")
        return ProcessorResult(outputs=[OutputItem("outputs/response.json", body)], processor_info="replicate_generic:v1", usage={}, extra={})

    return _runner
```

### Processor `main.py` (shared thin pattern)

```py
import os, sys, time, json
from libs.runtime_common.processor import parse_args, load_inputs, ensure_write_prefix
from libs.runtime_common.mode import resolve_mode
from libs.runtime_common.hashing import inputs_hash
from libs.runtime_common.fingerprint import compose_env_fingerprint
from libs.runtime_common.outputs import write_outputs, write_outputs_index
from libs.runtime_common.receipts import write_dual_receipts
from apps.core.processors.llm_litellm.provider import make_runner  # per processor

def main() -> int:
    args = parse_args()
    write_prefix = ensure_write_prefix(args.write_prefix)
    inputs = load_inputs(args.inputs)
    mode = resolve_mode(inputs).value  # raises on CI+real
    ih = inputs_hash(inputs)

    t0 = time.time()
    result = make_runner({})(inputs)
    duration_ms = int((time.time() - t0) * 1000)

    abs_paths = write_outputs(write_prefix, result.outputs)
    idx_path = write_outputs_index(args.execution_id, write_prefix, abs_paths)

    env_fp = compose_env_fingerprint(
        image=os.getenv("IMAGE_REF","unknown"), cpu=os.getenv("CPU","1"), memory=os.getenv("MEMORY","2Gi")
    )

    receipt = {
        "execution_id": args.execution_id,
        "processor_ref": os.getenv("PROCESSOR_REF","unknown"),
        "image_digest": os.getenv("IMAGE_REF","unknown"),
        "env_fingerprint": env_fp,
        "inputs_hash": ih["value"],
        "hash_schema": ih["hash_schema"],
        "outputs_index": str(idx_path),
        "processor_info": result.processor_info,  # string
        "usage": result.usage,
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "duration_ms": duration_ms,
        "mode": mode,
    }
    write_dual_receipts(args.execution_id, write_prefix, receipt)
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

## 10) Modal app (clean)

* Two entrypoints: `run(payload)` and `mock(payload)`; both use the same function signature.
* Functions annotated with `serialized=True` when custom names are set.
* No secret names hardcoded in code paths; the deploy workflow ensures presence.

*(You already have an updated `modal_app.py`; ensure both functions set `serialized=True` and that the “mock” entry clears keys and sets `payload["mode"]="mock"` before invoking the same executor.)*

## 11) CI Guardrails & Tests

* **Integration test:** `CI=true` + `--mode real` → command must exit non-zero (`ERR_CI_SAFETY`) **before** running a container.
* **Receipts:** assert required fields; image pin must include repo-scoped name.
* **Write prefix:** templates expand `{execution_id}`; actual files live under `<prefix>/outputs/…`; receipt at `<prefix>/receipt.json`.

## 12) FAQ (challenging questions)

**Q: Why callable providers instead of class `.run()`?**
A: Processors stay trivial: `runner(inputs)` — no polymorphism leakage, easy DI, easy tests.

**Q: Why `processor_info` as string?**
A: Stable human-readable field for receipts and diffs; avoids schema churn in acceptance tests.

**Q: Can we auto-detect mock mode from env?**
A: No. Single source of truth = `inputs["mode"]`. CI has only one extra rule: block `real`.

**Q: Should receipts be listed as outputs?**
A: No. Receipts are metadata; tests check receipt existence separately. Outputs list only artifacts.

**Q: Multi-arch images?**
A: Build & Pin emits manifest lists for `linux/amd64,linux/arm64`. Local fallback: `--build`.

**Q: Secrets drift between GitHub and Modal?**
A: CI sync step ensures presence by **name**. Processors read values from Modal env only.

---

### Success Criteria Recap

* All unit/integration/acceptance/property tests pass locally and in CI.
* Bot PR loop is idempotent (repo-scoped GHCR, stable naming).
* Modal deploy mock validation passes (functions redeployed after code changes).
* Logs are structured JSON; sensitive data redacted.
* No provider/Django coupling; processors remain self-contained.

This is the single source of truth the engineer should follow.
