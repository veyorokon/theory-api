# CI/CD Pipeline

This runbook documents the automated pipeline that builds processor images once, pins their digests, validates them locally, and then promotes the exact same artifacts through Modal **dev → staging → main**. Every section below maps directly to the workflows living in `.github/workflows/` (`pr-checks.yml`, `build-and-pin.yml`, `acceptance.yml`, `modal-deploy.yml`).

## High-Level Flow

```{mermaid}
graph TD
    PR[Pull Request → dev] --> Fast[PR Checks (lint/unit/docs)]
    Fast --> MergeDev[Merge to dev]
    MergeDev --> BP[Build & Pin (bot PR)]
    BP --> PinPR[Pin PR merged]
    PinPR --> Accept[Acceptance (Docker, mock mode)]
    Accept --> DeployDev[Modal Deploy → dev + smoke]
    DeployDev --> PromoteStg[Promote → staging]
    PromoteStg --> DeployStg[Modal Deploy → staging + smoke]
    DeployStg --> PromoteMain[Promote → main]
    PromoteMain --> DeployMain[Modal Deploy → main + smoke]
```

## Stage-by-Stage Summary

| Stage | Workflow | Trigger | Key Actions |
|-------|----------|---------|-------------|
| PR Checks | `pr-checks.yml` | PRs, pushes to `dev`/`main` | Ruff lint & format, unit tests (`pytest -m "unit and not integration"`), coverage, docs drift, deptry/deadcode |
| Build & Pin | `build-and-pin.yml` | Pushes to `dev`, manual dispatch | Build processor images once, push to GHCR, rewrite registry with digests, open bot PR if changes |
| Acceptance | `acceptance.yml` | Pushes to `dev` | Docker-compose stack, run `make test-acceptance` (adapter=`local`, mode=`smoke`), skip if any digest pending |
| Modal Deploy | `modal-deploy.yml` | Pushes to `dev`, `staging`, `main` | Sync secrets to Modal env, deploy pinned digests, smoke test each processor via Modal `smoke` function |

All downstream environments reuse the digests pinned on `dev`; **never rebuild** as part of staging/main promotion.

## 1. Pull Request Checks (Fast Lane)

The `pr-checks.yml` workflow enforces the following before merging into `dev`:

- **Linting & formatting**: `ruff check` and `ruff format --check` on the `code/` tree.
- **Unit tests**: executed inside `code/` using SQLite (`DJANGO_SETTINGS_MODULE=backend.settings.unittest`). Only tests marked `unit` run.
- **Coverage**: `make test-coverage` produces `coverage.xml` & `coverage.json` and enforces a baseline threshold.
- **Docs & drift**: `make docs` runs the docs export, drift check, and Sphinx build with `-W`.
- **Static guards**: dead-code gate, deptry, import reachability.

> Need Docker-based checks pre-merge? Label the PR with `run-acceptance` and manually run the acceptance workflow.

## 2. Build & Pin (Image Factory)

Workflow: `.github/workflows/build-and-pin.yml`

### Permissions & Checkout

```yaml
permissions:
  contents: write
  packages: write
  pull-requests: write

steps:
  - uses: actions/checkout@v4
    with:
      fetch-depth: 0
      persist-credentials: true
```

### Processor Matrix Resolution

- Read `code/apps/core/registry/processors/*.yaml`.
- For each entry capture: registry path, processor package (`code/apps/core/processors/<name>`), Dockerfile location.
- Optional workflow input `processors` limits the build list.

### Build & Push

- `docker setup-buildx-action` enables BuildKit.
- Each processor is built with context `code/` (Dockerfile lives under the processor dir).
- Images are tagged `ghcr.io/<repo>/<processor>:build-<timestamp>` and pushed (single arch `linux/amd64`; extend if needed).
- Digests are extracted via `docker buildx imagetools inspect`.

### Update Registry & Bot PR

- Registry YAMLs are rewritten so `image.oci` points to `<image>@sha256:<digest>`.
- A change detector runs: `git diff --quiet -- code/apps/core/registry/processors`.
- If differences exist, `peter-evans/create-pull-request@v6` opens `bot/pin-${{ github.run_id }}` with commit message `ci: pin processor images (bot)`.

**Important:** GHCR packages must exist and grant this repository **Actions: Write**.

#### Onboarding a New Processor Package

1. Build & push an initial tag locally to create the GHCR package:
   ```bash
   cd code/apps/core/processors/replicate_generic
   docker build -t ghcr.io/<owner>/<repo>/replicate-generic:initial .
   echo "$GH_PAT" | docker login ghcr.io -u <user> --password-stdin
   docker push ghcr.io/<owner>/<repo>/replicate-generic:initial
   ```
2. GitHub → Packages → (package) → Settings → Repository access → add this repo with **Actions: Write**.
3. Subsequent automated pushes from the workflow will succeed.

## 3. Acceptance Tests (Docker, Smoke Mode)

Workflow: `.github/workflows/acceptance.yml`

- Runs on pushes to `dev` after the pin PR merges.
- Early guard: exits if any registry YAML still contains `oci: sha256:pending`.
- Starts Docker services via `docker compose up -d postgres redis minio`.
- Runs `make test-acceptance` inside `code/` (adapter=`local`, `--mode smoke`), exercising budgets, artifact writes, and receipts.
- Ensure branch protection on `dev` requires this workflow before deploy.

## 4. Modal Deploy & Smoke

Workflow: `.github/workflows/modal-deploy.yml`

### Trigger Strategy

- Pushes to `dev`, `staging`, `main` (optionally manual `workflow_dispatch`).
- Each branch deploys to its matching Modal environment (`MODAL_ENVIRONMENT` defaults to the branch name).

### Steps

1. **Checkout** repo (full history not required).
2. **Collect processors**: parse registry YAML into JSON (ref, pinned digest, secret list).
3. **Secret sync**: for every secret name listed, read matching GitHub secret and `modal secret create <name> --env $ENV --force`. Missing GitHub secrets emit warnings.
4. **Deploy**: invoke `modal deploy -m code/modal_app.py --env $ENV` for each processor with `PROCESSOR_REF`, `IMAGE_REF`, `TOOL_SECRETS` in the environment. This deploys the pinned digest.
5. **Post-deploy smoke**: call `modal function call code.modal_app::smoke --env $ENV --args '{"ref":"...","mode":"mock"}'` to verify the deployment without touching external providers.

### Promotion Philosophy

- **Build once** on `dev` → reuse digests for `staging` and `main`.
- Promotion is simply merging the same registry YAML commit across branches.
- Optional: after staging deploy, run a single “real mode” canary invocation if quotas allow.

## Secrets & Configuration

- Processor registry YAMLs declare required/optional secrets. Example:
  ```yaml
  secrets:
    required:
      - OPENAI_API_KEY
    optional:
      - LITELLM_API_BASE
  ```
- GitHub is the source of truth. Store per-environment values as repository/environment secrets with consistent names (`OPENAI_API_KEY_DEV`, etc.). The deploy workflow reads them and pushes to Modal.
- `REGISTRY_AUTH` must be present in each Modal env (credentials for pulling from GHCR).

## Promotion Checklist

1. Merge pin PR → `dev`. Confirm Acceptance (Docker) and Modal deploy (dev) are green.
2. Promote to `staging` (merge or cherry-pick). Modal deploy (staging) runs automatically and smokes succeed.
3. Promote to `main`. Modal deploy (main) runs, smoke succeed.
4. Downstream Django releases can now assume the processors are deployed with the pinned digests.

Rollback is mechanical: revert the pin commit on `dev`, merge through staging/main, and rerun deploy.

## Workflow Reference

| File | Purpose |
|------|---------|
| `.github/workflows/pr-checks.yml` | Fast lane: lint, unit, docs, coverage |
| `.github/workflows/build-and-pin.yml` | Build processor images once, pin digests, open bot PR |
| `.github/workflows/acceptance.yml` | Docker-based acceptance on `dev` using mock mode |
| `.github/workflows/modal-deploy.yml` | Deploy & smoke processors on Modal dev/staging/main |

Keep this runbook in sync with workflow changes—update both together whenever CI/CD behavior shifts.
