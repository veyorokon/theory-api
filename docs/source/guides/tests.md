# Testing Guidebook — Local, Modal (dev), and CI/CD (mock & real)

This guide is the single source of truth for exercising processors and adapters across both `local` and `modal` adapters, both execution modes (`mock`, `real`), and pinned digests. Follow these lanes and what passes locally will pass in CI/CD.

---

## 0. Safety Rails (read first)

- **Supported modes**: only `mock` and `real`.
- **CI guard**: when `CI=true`, `mode=real` is blocked. Real-mode runs are local-only (or out-of-band jobs with explicit approvals).
- **Logging**: processors emit structured logs and support `/run-stream` (SSE). Envelopes are returned as JSON from `/run` or as the final `settle` event from `/run-stream`.
- **Secrets discipline**:
  - `mock`: providers must not read secrets; unset them.
  - `real`: secrets must be present in your shell, and (for modal) in the target Modal environment.

---

## 1. Test Matrix (where + how)

| Where you run             | Adapter                          | Artifacts                                                          | Mode                    | Allowed in CI? | Purpose                                              |
| ------------------------- | -------------------------------- | ------------------------------------------------------------------ | ----------------------- | -------------- | ---------------------------------------------------- |
| Local PR-parity           | `local`                          | **Build-from-source** (`--build` or `RUN_PROCESSOR_FORCE_BUILD=1`) | `mock`                  | ✅              | Dev loop, PR lane parity                             |
| Local supply-chain parity | `local`                          | **Pinned** digests                                               | `mock`                  | ✅              | Validate against pinned digests                      |
| Local “real”              | `local`                          | Build or pinned                                                    | `real`                  | ❌ (local only) | Exercise actual provider calls                       |
| Modal dev mock            | `modal` ( `MODAL_ENVIRONMENT=dev` ) | n/a                                                              | `mock`                  | ✅              | Adapter + app routing, hermetic                      |
| Modal dev real            | `modal` ( `MODAL_ENVIRONMENT=dev` ) | n/a                                                              | `real`                  | ❌ (local only) | End-to-end provider calls via Modal                  |
| CI PR lane                | `local`                          | Build-from-source                                                  | `mock`                  | ✅              | Fast, hermetic verification of current source        |
| CI staging/main           | `local` → `modal`                | **Pinned** → Deploy                                                | `mock` (+ gated probes) | ✅              | Supply-chain: pins, acceptance, deploy, smoke/canary |

> **Pinned** means the digest recorded in `code/apps/core/processors/**/registry.yaml`.

---

## 2. Make Targets (local & CI)

These match the CI workflows exactly—run them locally first:

```bash
# Fast unit tests (SQLite) — no Docker, no network
make test-unit

# Integration tests (hermetic subprocesses)
make test-integration

# PR lane acceptance — build-from-source, mock, no secrets
make test-acceptance-pr

# Supply-chain acceptance — pinned digests, mock, no secrets
make test-acceptance-dev
```

Each target fails fast if zero tests match the marker expression, so you’ll know immediately when a lane has been mis-marked.

CI lanes reuse the same targets:

- **PR workflow (`pr-tests.yml`)**: `test-unit`, `test-integration`, `test-acceptance-pr`
- **Dev branch (`dev-tests.yml`)**: `test-acceptance-dev`
- **Staging (`staging-pipeline.yml`)**: Build & Pin → `test-acceptance-dev` → deploy + smoke/negative probe
- **Main (`main-pipeline.yml`)**: `test-acceptance-dev` → deploy + smoke/negative probe

---

## 3. Environment Setup (local)

Common boilerplate:

```bash
cd code
export DJANGO_SETTINGS_MODULE=backend.settings.unittest
export LOG_STREAM=stderr           # processors log to stderr; envelopes come from HTTP responses
```

> The Make targets set `LOG_STREAM` for you; only export it manually when running ad-hoc commands.

### 3.1 PR-lane parity — build-from-source, mock

Knob: `RUN_PROCESSOR_FORCE_BUILD=1` (or pass `--build`).

```bash
export RUN_PROCESSOR_FORCE_BUILD=1
python manage.py run_processor \
  --ref llm/litellm@1 \
  --adapter local \
  --mode mock \
  --write-prefix "/artifacts/outputs/dev/{execution_id}" \
  --inputs-json '{"schema":"v1","params":{"messages":[{"role":"user","content":"hi"}]}}' \
  --json 1>/tmp/result.json 2>/tmp/logs.ndjson
```

Or simply: `make test-acceptance-pr`

### 3.2 Supply-chain parity — pinned-only, mock

Knob: `RUN_PROCESSOR_FORCE_BUILD=0` (default).

```bash
export RUN_PROCESSOR_FORCE_BUILD=0
python manage.py run_processor \
  --ref llm/litellm@1 \
  --adapter local \
  --mode mock \
  --write-prefix "/artifacts/outputs/dev/{execution_id}" \
  --inputs-json '{"schema":"v1","params":{"messages":[{"role":"user","content":"hi"}]}}' \
  --json
```

Equivalent: `make test-acceptance-dev`

> If your GHCR registry is private, run `docker login ghcr.io` before the pinned suite.

### 3.3 Local “real” mode (provider calls)

Not allowed in CI. Provide real secrets locally:

```bash
export OPENAI_API_KEY=sk-...           # set the secrets your processor needs
export RUN_PROCESSOR_FORCE_BUILD=1     # or 0, your choice
python manage.py run_processor \
  --ref llm/litellm@1 \
  --adapter local \
  --mode real \
  --write-prefix "/artifacts/outputs/dev/{execution_id}" \
  --inputs-json '{"schema":"v1","params":{"messages":[{"role":"user","content":"hi"}]}}' \
  --json
```

Expected: a success envelope with real model outputs; receipts include secret **names** only (never values).

### 3.4 Modal dev — mock & real

The dev Modal environment is developer-owned; CI never deploys here. Naming convention for sandbox apps: `<branch>-<user>-<processor-slug>-vX` (e.g., `feat-retries-alex-llm-litellm-v1`). Deploy via `python code/manage.py deploy_modal --env dev`, the CLI, or the Make helpers below.

```bash
# Full loop: build → deploy → mock smoke test
make modal-dev-workflow REF=llm/litellm@1

# Mix-and-match individual steps if you need manual control
make build-processor REF=llm/litellm@1
make deploy-modal-dev REF=llm/litellm@1
make smoke-modal-dev REF=llm/litellm@1

# Optional: real-mode probe (requires local + Modal secrets)
make real-modal-dev REF=llm/litellm@1
```

**Mock via Modal (dev):**

```bash
export MODAL_ENABLED=true
export MODAL_ENVIRONMENT=dev
python manage.py run_processor \
  --ref llm/litellm@1 \
  --adapter modal \
  --mode mock \
  --write-prefix "/artifacts/outputs/dev/{execution_id}" \
  --inputs-json '{"schema":"v1","params":{"messages":[{"role":"user","content":"hi"}]}}' \
  --json
```

**Real via Modal (dev):**

```bash
export MODAL_ENABLED=true
export MODAL_ENVIRONMENT=dev
export OPENAI_API_KEY=sk-...        # secret must also exist in the Modal env (by name)
python manage.py run_processor \
  --ref llm/litellm@1 \
  --adapter modal \
  --mode real \
  --write-prefix "/artifacts/outputs/dev/{execution_id}" \
  --inputs-json '{"schema":"v1","params":{"messages":[{"role":"user","content":"hi"}]}}' \
  --json
```

> Crashes still return canonical error envelopes. CI smoke jobs wrap calls in per-command timeouts to avoid hangs.

---

## 4. Canonical Outputs

**Success envelope (minimal):**

```json
{
  "status": "success",
  "execution_id": "UUID",
  "outputs": [
    {
      "path": "/artifacts/outputs/dev/<id>/outputs/response.json",
      "cid": "b3:...",
      "size_bytes": 114,
      "mime": "application/json"
    }
  ],
  "index_path": "/artifacts/outputs/dev/<id>/outputs.json",
  "meta": {
    "image_digest": "ghcr.io/...@sha256:...",
    "env_fingerprint": "cpu:1;image:...;memory:2gb;secrets:OPENAI_API_KEY",
    "duration_ms": 123
  }
}
```

**Error envelope:**

```json
{
  "status": "error",
  "execution_id": "UUID",
  "error": {"code": "ERR_*", "message": "safe message"},
  "meta": {"env_fingerprint": "cpu:1;image:...;memory:2gb;secrets:OPENAI_API_KEY"}
}
```

**Receipts** live at `<write_prefix>/receipt.json` and `/artifacts/execution/<execution_id>/determinism.json`, and capture digest, inputs hash, fingerprint, and output index references.

---

## 5. CI/CD Mapping (why parity matters)

### Pull Requests

- Executes `make test-unit`, `make test-integration`, `make test-acceptance-pr`.
- Guarantees hermetic, build-from-source coverage in `mock` mode with no secrets.

### Staging

- Build & Pin (multi-arch) only for processors that changed.
- `make test-acceptance-dev` (pinned digests, mock) ensures reproducibility.
- Deploy to Modal staging using pinned digests, then run smoke (`mode=mock`) and a negative probe (`mode=real` expecting `ERR_MISSING_SECRET`). Optional canaries live behind feature flags.

### Main

- Reuses the pins promoted from staging. Same acceptance + deploy + drift audit pipeline, targeting production secrets and environment.

---

## 6. Typical Local Flows

```bash
# Day-to-day loop
make test-unit
make test-integration
make test-acceptance-pr

# Preview what staging/main will exercise
make test-acceptance-dev

# Exercise Modal adapter (dev env)
make modal-dev-workflow REF=llm/litellm@1
# or drive it manually with MODAL_ENABLED=true ... as shown above

# Real mode (never in CI)
export OPENAI_API_KEY=sk-...
python manage.py run_processor --ref llm/litellm@1 --adapter local --mode real \
  --write-prefix "/artifacts/outputs/dev/{execution_id}" --inputs-json '{"schema":"v1","params":{"messages":[...]}}' --json
```

---

## 7. Secrets & Registry-Driven Discovery

- Tests auto-discover required secret names from the processor registry (`tests/tools/registry.py`).
- Mock lanes must drop all secrets; real lanes must provide them.
- Modal deployments expect secrets to be present in the Modal environment **under the same names** defined in the registry.

---

## 8. Troubleshooting

- **PR acceptance fails but unit passes** → verify `RUN_PROCESSOR_FORCE_BUILD=1` or use the Make target.
- **Pinned acceptance fails locally** → your registry pins are stale; rebase or wait for staging’s Build & Pin commit.
- **Modal dev errors** → ensure app naming matches `<branch>-<user>-<slug>-vX`, inputs satisfy payload validation, and secrets exist in Modal.
- **Streaming issues** → consume `/run-stream` SSE events (`log|progress|settle`); final `settle` contains the envelope.

---

## 9. FAQ

**Can CI run `mode=real`?** No. The guardrail intentionally blocks real-mode executions. Use local runs or controlled staging jobs outside the default workflows.

**Do I need Docker for PR acceptance?** Yes—the `local` adapter suite uses docker-compose services.

**How do I mirror CI locally?** Use the provided Make targets; they wrap the same markers, env vars, and docker-compose orchestration that CI invokes.

Follow this guide and you get deterministic parity between local development and every CI/CD lane, with optional Modal dev and real-mode explorations handled safely.
