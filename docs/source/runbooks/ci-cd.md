# CI/CD Pipeline

This runbook captures the three-lane delivery system: PRs build directly from source, staging owns supply-chain promotion (build → pin → accept → deploy), and main redeploys the exact pinned artifacts to production. Local developers stay fast and hermetic; CI branches stay serialized and deterministic.

## Order of Operations

| Stage | Workflow(s) | What runs | Artifact under test |
|-------|-------------|-----------|---------------------|
| Local development | N/A | `make compose-up`, `make test-acceptance-pr` | Working tree (local Docker build, mock mode) |
| Pull Request lane | `.github/workflows/pr-tests.yml` | `make test-unit`, `make test-integration`, `make test-acceptance-pr` | Source-built containers (hermetic, `--build`, `mode=mock`) |
| `dev` branch | `.github/workflows/dev-tests.yml` | Sanity sweep (`test-unit`, `test-integration`, `test-acceptance-dev`) | Latest merge commit with pinned registry (no rebuild) |
| `staging` pipeline | `.github/workflows/staging-pipeline.yml` | 1) Build & pin → 2) Acceptance (pinned) → 3) Deploy Modal staging → 4) Drift audit | Newly built multi-arch images; pins written to `staging` |
| Release PR | Manual | Open `staging → main` PR referencing pinned commit | Pins + code from validated staging commit |
| `main` pipeline | `.github/workflows/main-pipeline.yml` | Acceptance (pinned) → Deploy Modal (digest) → Drift audit | Same digests promoted from staging |

### 1. Local Development

- Goal: quick iteration with full docker-compose stack plus optional Modal **dev** sandboxing.
- Run `make compose-up` to boot Postgres/Redis/MinIO, then `make test-acceptance-pr` for the PR lane suite (`--build`, `mode=mock`, no secrets).
- Developers can deploy to Modal **dev** manually (`python code/manage.py deploy_modal --env dev`); CI never touches this environment.

### 2. Pull Request Lane (Hermetic Source Builds)

- Trigger: PRs targeting `dev`, `staging`, or `main`.
- Workflow: `pr-tests.yml`.
- Jobs: unit + integration tests (SQLite, hermetic), then `make test-acceptance-pr` behind docker-compose services.
- Secrets: explicitly unset; lane must succeed without external credentials.
- Exit criteria: workflow must be green before merge.

### 3. `dev` Branch (Post-Merge Sanity)

- Trigger: push to `dev`.
- Workflow: `dev-tests.yml`.
- Purpose: ensure the merged commit still passes unit/integration and the **supply-chain** acceptance suite (`make test-acceptance-dev`) using the currently pinned digests. No image builds or deploys occur here.
- Modal deployments: skipped; `dev` is for code integration only.

### 4. `staging` Pipeline (Supply-Chain Owner)

- Trigger: push to `staging` (usually merge-up from `dev`).
- Steps run serially via `needs`:
  1. **Build & Pin** – Multi-arch (`amd64` + `arm64`) builds for each processor. Digests are written directly back to `staging` via commit `ci(staging): pin processor images`. No bot PRs against other branches.
     - Build sequence: `make build-processor REF=<ref> PLATFORMS=linux/arm64 && make pin-processor REF=<ref> PLATFORMS=linux/arm64`
     - Then: `make build-processor REF=<ref> PLATFORMS=linux/amd64 && make pin-processor REF=<ref> PLATFORMS=linux/amd64`
     - Registry.yaml now contains both platform digests
  2. **Acceptance (pinned)** – Executes `make test-acceptance-dev` with `TEST_LANE=staging`, verifying per-processor registry digests in mock mode (no rebuilds).
     - Orchestrator selects digest based on platform: amd64 for Modal, arm64 for local Mac
  3. **Deploy Modal (staging)** – Deploys by amd64 digest (`modalctl deploy`), runs smoke (`mode=mock`) and a negative probe (`mode=real` expecting `ERR_MISSING_SECRET`).
     - Modal always uses amd64 digest from `registry.yaml::image.platforms.amd64`
  4. **Drift Audit** – `python code/scripts/drift_audit.py` fails if deployed digests mismatch the registry.
- Outcome: staging now owns canonical pins plus a green deployment. Open a release PR from this commit to `main`.

### 5. Release PR (`staging → main`)

- Manual step to promote staging’s validated commit into production history.
- PR title convention: `Promote staging → main @ <sha>`.
- Only contains code + registry changes already tested in staging.

### 6. `main` Pipeline (Production Deploy)

- Trigger: merge of the release PR.
- Steps mirror staging minus builds: acceptance (pinned), Modal deploy (production secrets), smoke + negative probe, then drift audit.
- Guarantees production runs exactly the bits that passed staging.

## Test Lanes & Make Targets

- `make test-unit` / `make test-integration` – hermetic SQLite/pytest flows for fast feedback.
- `make test-acceptance-pr` – PR lane acceptance; composes services, forces `BUILD=1`, requires docker, uses mock mode.
- `make test-acceptance-dev` – Supply-chain acceptance; reuses pinned artifacts, still mock mode, hermetic.
- `make test-smoke` – Post-deploy smoke markers (`deploy_smoke`).
- Pytest markers live in `pytest.ini` and `tests/tools/markers.py`; strict markers enforce taxonomy (unit/integration/contracts/property/acceptance/prlane/supplychain/etc.).

## Modal Environments & Naming

- **dev (personal)** – `<branch>-<user>-<processor-slug>-vX`; never touched by CI.
- **staging/main** – `<processor-slug>-vX`; CI deploys via `modalctl deploy` using pinned digests.
- Negative probes intentionally trigger `ERR_MISSING_SECRET` to confirm real-mode guardrails are intact.

## Secrets & Registry Expectations

- Processor specs (`code/apps/core/processors/**/registry.yaml`) declare platform digests and `secrets.required`.
- Registry contains both `amd64` and `arm64` digests:
  ```yaml
  image:
    platforms:
      amd64: ghcr.io/veyorokon/theory-api/llm-litellm@sha256:a4f41889...
      arm64: ghcr.io/veyorokon/theory-api/llm-litellm@sha256:f41c4e79...
  ```
- Orchestrator platform selection:
  - Modal adapter: always selects `amd64` (Modal runs x86_64)
  - Local adapter: selects host platform (arm64 on Mac M1/M2, amd64 on x86_64)
  - Override with `--platform` parameter if needed
- Staging build job must have package write access to GHCR; production pipelines only need read.
- Modal secrets pull from branch-scoped GitHub secrets (`OPENAI_API_KEY_STAGING`, `OPENAI_API_KEY_PROD`, etc.).
- Drift audits compare deployed app metadata with registry digests; treat failures as stop-the-line events.

## Workflow Reference

| File | Purpose |
|------|---------|
| `.github/workflows/pr-tests.yml` | PR lane hermetic tests (unit, integration, acceptance-pr) |
| `.github/workflows/dev-tests.yml` | Post-merge sanity suite on `dev` (no builds or deploys) |
| `.github/workflows/staging-pipeline.yml` | Build → pin → acceptance → deploy (staging) → drift |
| `.github/workflows/main-pipeline.yml` | Acceptance → deploy (prod) → drift using staging pins |

Keep this runbook aligned with workflow edits and the pytest taxonomy; when the lane model changes, update this document in the same PR.
