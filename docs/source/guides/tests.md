# Testing Guidebook — Local, Modal (dev), and CI/CD (mock & real)

This guide is the single source of truth for exercising processors and adapters across both `local` and `modal` adapters, both execution modes (`mock`, `real`), and pinned digests. Follow these lanes and what passes locally will pass in CI/CD.

---

## 0. Safety Rails (read first)

- **Supported modes**: only `mock` and `real`.
- **CI guard**: when `CI=true`, `mode=real` is blocked. Real-mode runs are local-only (or out-of-band jobs with explicit approvals).
- **Logging**: processors emit structured logs via WebSocket. Envelopes are returned as JSON from final `RunResult` frame.
- **Secrets discipline**:
  - `mock`: providers must not read secrets; unset them.
  - `real`: secrets must be present. Local: injected at container start. Modal: synced to environment.

---

## 1. Test Matrix (where + how)

| Where you run             | Adapter | Container Start | Mode  | Allowed in CI? | Purpose                                   |
| ------------------------- | ------- | --------------- | ----- | -------------- | ----------------------------------------- |
| Local PR-parity           | local   | `localctl start` (newest build) | mock  | ✅              | Dev loop, PR lane parity                  |
| Local supply-chain parity | local   | `localctl start` (pinned digest) | mock  | ✅              | Validate against pinned digests           |
| Local "real"              | local   | `localctl start` (build or pinned) | real  | ❌ (local only) | Exercise actual provider calls            |
| Modal dev mock            | modal   | `modalctl start --env dev` | mock  | ✅              | Adapter + app routing, hermetic           |
| Modal dev real            | modal   | `modalctl start --env dev` | real  | ❌ (local only) | End-to-end provider calls via Modal       |
| CI PR lane                | local   | Build-from-source | mock  | ✅              | Fast, hermetic verification of current source |
| CI staging/main           | modal   | Pinned → Deploy | mock (+ gated probes) | ✅              | Supply-chain: pins, acceptance, deploy, smoke |

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

Each target fails fast if zero tests match the marker expression, so you'll know immediately when a lane has been mis-marked.

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
export LOG_STREAM=stderr           # processors log to stderr; envelopes come from WebSocket
```

> The Make targets set `LOG_STREAM` for you; only export it manually when running ad-hoc commands.

### 3.1 PR-lane parity — build-from-source, mock

Start container from newest build, run processor:

```bash
# Start container (will use newest build tag)
OPENAI_API_KEY=$OPENAI_API_KEY python manage.py localctl start --ref llm/litellm@1

# Run processor
python manage.py localctl run \
  --ref llm/litellm@1 \
  --mode mock \
  --write-prefix "/artifacts/outputs/dev/{execution_id}" \
  --inputs-json '{"schema":"v1","params":{"messages":[{"role":"user","content":"hi"}]}}' \
  --json 1>/tmp/result.json 2>/tmp/logs.ndjson

# Stop when done
python manage.py localctl stop --ref llm/litellm@1
```

Or simply: `make test-acceptance-pr`

### 3.2 Supply-chain parity — pinned-only, mock

Start container from pinned digest, run processor:

```bash
# Start container (will use pinned digest from registry.yaml)
OPENAI_API_KEY=$OPENAI_API_KEY python manage.py localctl start --ref llm/litellm@1

# Run processor
python manage.py localctl run \
  --ref llm/litellm@1 \
  --mode mock \
  --write-prefix "/artifacts/outputs/dev/{execution_id}" \
  --inputs-json '{"schema":"v1","params":{"messages":[{"role":"user","content":"hi"}]}}' \
  --json

# Stop when done
python manage.py localctl stop --ref llm/litellm@1
```

Equivalent: `make test-acceptance-dev`

> If your GHCR registry is private, run `docker login ghcr.io` before the pinned suite.

### 3.3 Local "real" mode (provider calls)

Not allowed in CI. Provide real secrets at container start:

```bash
# Start container with real secrets
export OPENAI_API_KEY=sk-...           # set the secrets your processor needs
python manage.py localctl start --ref llm/litellm@1

# Run processor in real mode
python manage.py localctl run \
  --ref llm/litellm@1 \
  --mode real \
  --write-prefix "/artifacts/outputs/dev/{execution_id}" \
  --inputs-json '{"schema":"v1","params":{"messages":[{"role":"user","content":"hi"}]}}' \
  --json

# Stop when done
python manage.py localctl stop --ref llm/litellm@1
```

Expected: a success envelope with real model outputs; receipts include secret **names** only (never values).

### 3.4 Modal dev — mock & real

The dev Modal environment is developer-owned; CI never deploys here. Naming convention: `<branch>-<user>-<processor-slug>` (e.g., `feat-retries-alex-llm-litellm-v1`).

**Deploy workflow:**

```bash
# Build image (if needed)
python manage.py processorctl build --ref llm/litellm@1 --platforms linux/amd64

# Deploy to Modal dev
GIT_BRANCH=feat/test GIT_USER=veyorokon \
  python manage.py modalctl start \
    --ref llm/litellm@1 \
    --env dev \
    --oci ghcr.io/veyorokon/theory-api/llm-litellm@sha256:abc...

# Sync secrets
python manage.py modalctl sync-secrets --ref llm/litellm@1 --env dev
```

**Mock via Modal (dev):**

```bash
# Run processor in mock mode
python manage.py modalctl run \
  --ref llm/litellm@1 \
  --mode mock \
  --write-prefix "/artifacts/outputs/dev/{execution_id}" \
  --inputs-json '{"schema":"v1","params":{"messages":[{"role":"user","content":"hi"}]}}' \
  --json
```

**Real via Modal (dev):**

```bash
# Secret must exist in Modal environment (synced via modalctl sync-secrets)
python manage.py modalctl run \
  --ref llm/litellm@1 \
  --mode real \
  --write-prefix "/artifacts/outputs/dev/{execution_id}" \
  --inputs-json '{"schema":"v1","params":{"messages":[{"role":"user","content":"hi"}]}}' \
  --json
```

**Stop when done:**

```bash
python manage.py modalctl stop --ref llm/litellm@1 --env dev
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
- Containers started via `localctl start` (newest build tag).

### Staging

- Build & Pin (multi-arch) only for processors that changed via `processorctl build/push/pin`.
- `make test-acceptance-dev` (pinned digests, mock) ensures reproducibility.
- Deploy to Modal staging using `modalctl start --env staging --oci <digest>`.
- Sync secrets via `modalctl sync-secrets --env staging`.
- Run smoke (`mode=mock`) and negative probe (`mode=real` expecting `ERR_MISSING_SECRET`).

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
# 1. Build
python manage.py processorctl build --ref llm/litellm@1 --platforms linux/amd64

# 2. Deploy
GIT_BRANCH=feat/test GIT_USER=veyorokon \
  python manage.py modalctl start --ref llm/litellm@1 --env dev --oci <digest>

# 3. Sync secrets
python manage.py modalctl sync-secrets --ref llm/litellm@1 --env dev

# 4. Run
python manage.py modalctl run --ref llm/litellm@1 --mode mock --json

# 5. Stop
python manage.py modalctl stop --ref llm/litellm@1 --env dev

# Real mode (never in CI)
export OPENAI_API_KEY=sk-...
python manage.py localctl start --ref llm/litellm@1
python manage.py localctl run --ref llm/litellm@1 --mode real \
  --write-prefix "/artifacts/outputs/dev/{execution_id}" \
  --inputs-json '{"schema":"v1","params":{"messages":[...]}}' --json
python manage.py localctl stop --ref llm/litellm@1
```

---

## 7. Secrets & Registry-Driven Discovery

- Tests auto-discover required secret names from the processor registry (`tests/tools/registry.py`).
- Mock lanes must drop all secrets; real lanes must provide them.
- **Local**: Secrets injected at container start time via `localctl start`.
- **Modal**: Secrets synced separately via `modalctl sync-secrets` after deployment.
- Modal deployments expect secrets to be present in the Modal environment **under the same names** defined in the registry.

---

## 8. Troubleshooting

- **PR acceptance fails but unit passes** → verify container started with newest build via `localctl start`.
- **Pinned acceptance fails locally** → your registry pins are stale; rebase or wait for staging's Build & Pin commit.
- **Modal dev errors** → ensure app naming matches `<branch>-<user>-<slug>`, inputs satisfy payload validation, and secrets exist in Modal via `modalctl sync-secrets`.
- **Container not running** → use `localctl status` to check running containers; ensure `localctl start` completed successfully.
- **Secrets missing** → Local: provide at start time. Modal: sync via `modalctl sync-secrets`.

---

## 9. FAQ

**Can CI run `mode=real`?** No. The guardrail intentionally blocks real-mode executions. Use local runs or controlled staging jobs outside the default workflows.

**Do I need Docker for PR acceptance?** Yes—the `local` adapter suite uses docker-compose services and containers via `localctl`.

**How do I mirror CI locally?** Use the provided Make targets; they wrap the same markers, env vars, and docker-compose orchestration that CI invokes.

**Do containers auto-start?** No. Explicit `localctl start` or `modalctl start` required before running processors.

**Where are secrets injected?** Local: at `localctl start` time. Modal: synced via `modalctl sync-secrets` after `modalctl start`.

Follow this guide and you get deterministic parity between local development and every CI/CD lane, with optional Modal dev and real-mode explorations handled safely.
