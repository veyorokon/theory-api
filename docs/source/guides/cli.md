# CLI Reference

Command-line interfaces for processor execution and Modal deployment.

## run_processor

Execute processors across WebSocket adapters with explicit mode selection.

### Basic Usage

```bash
python manage.py run_processor \
  --ref llm/litellm@1 \
  --adapter local \
  --mode mock \
  --write-prefix /artifacts/outputs/text/ \
  --inputs-json '{"schema":"v1","params":{"messages":[{"role":"user","content":"Hello"}]}}' \
  --json
```

### Parameters

- `--ref` (required): Processor reference (e.g. `llm/litellm@1`)
- `--adapter` (required): `local` or `modal`
- `--mode` (optional): `mock` (default) or `real`
- `--platform` (optional): Override platform for digest selection (`amd64` or `arm64`). Defaults: `amd64` for modal, host platform for local.
- `--write-prefix` (optional): Output prefix (default `/artifacts/outputs/`). Must include `{execution_id}` to prevent collisions.
- **JSON Input Options** (mutually exclusive):
  - `--inputs-json` (recommended): Direct JSON input (no escaping required)
  - `--inputs-file PATH`: Read JSON from file (version control friendly)
  - `--inputs -`: Read JSON from stdin (heredoc/pipe friendly)
  - `--inputs-jsonstr` (deprecated): Legacy escaped string format
- `--adapter-opts-json` (optional): Adapter-specific options
- `--plan`, `--attach`, `--json`, `--save-dir`, `--save-first`: unchanged

> The legacy `--adapter mock` shim has been removed. Use `--mode mock` with the local adapter instead.

### Mode Behaviour

| Mode | Effect |
|------|--------|
| `mock` | No external network calls; deterministic outputs via WebSocket |
| `real` | Full container execution (local) or Modal WebSocket with real provider calls |

### Image Selection (`--build`)

The `--build` flag affects only the local adapter:

- `local + --build=true` → use the newest locally built, timestamped tag (build-from-source loop)
- `local + --build=false` (default) → use the pinned registry digest from the per-processor `registry.yaml`
- `modal + --build=any` → ignored; the adapter performs an SDK lookup of the deployed WebSocket app/function (deployment is pinned by digest)

Example:

```bash
# Build-from-source loop (local only)
python manage.py run_processor --ref ns/name@1 --adapter local --mode mock --build --json

# Pinned digest (supply-chain parity)
python manage.py run_processor --ref ns/name@1 --adapter local --mode mock --json

# Modal ignores --build
python manage.py run_processor --ref ns/name@1 --adapter modal --mode mock --json
```

### Storage Backend Configuration

Processors support MinIO (dev) and S3 (prod) via environment variables:

#### MinIO (Development)
```bash
# Using canonical minio.local:9000 endpoint
STORAGE_BACKEND=minio \
MINIO_STORAGE_ENDPOINT=minio.local:9000 \
MINIO_STORAGE_ACCESS_KEY=minioadmin \
MINIO_STORAGE_SECRET_KEY=minioadmin \
MINIO_STORAGE_USE_HTTPS=false \
python manage.py run_processor --ref llm/litellm@1 --adapter local --mode mock --json
```

#### S3 (Production)
```bash
# Using AWS S3 with IAM credentials
STORAGE_BACKEND=s3 \
AWS_ACCESS_KEY_ID=your-access-key-id \
AWS_SECRET_ACCESS_KEY=your-secret-access-key \
ARTIFACTS_BUCKET=theory-artifacts-dev \
ARTIFACTS_REGION=us-east-1 \
python manage.py run_processor --ref llm/litellm@1 --adapter local --mode mock --json
```

See {doc}`../apps/storage` for storage adapter details and Terraform setup in `terraform/s3.tf`.

### Examples

```bash
# Local WebSocket mock run (fast smoke test)
python manage.py run_processor --ref llm/litellm@1 --adapter local --mode mock --json

# Local WebSocket real run (Docker)
python manage.py run_processor --ref llm/litellm@1 --adapter local --mode real

# Modal WebSocket mock run with S3 storage
STORAGE_BACKEND=s3 \
AWS_ACCESS_KEY_ID=your-access-key-id \
AWS_SECRET_ACCESS_KEY=your-secret-access-key \
ARTIFACTS_BUCKET=theory-artifacts-dev \
ARTIFACTS_REGION=us-east-1 \
BRANCH=feat/websocket-standardization \
USER=veyorokon \
MODAL_ENVIRONMENT=dev \
python manage.py run_processor \
  --ref llm/litellm@1 --adapter modal --mode mock \
  --write-prefix "/artifacts/outputs/modal-s3-test/{execution_id}/" \
  --inputs-json '{"schema":"v1","params":{"messages":[{"role":"user","content":"Test"}],"model":"gpt-4o-mini"}}' \
  --json

# Envelopes are returned via WebSocket; use --json to pretty-print in CLI context
python manage.py run_processor ... --json 1>result.json 2>logs.ndjson
```

## modalctl (deploy/verify/status/logs/sync-secrets)

Unified Modal control plane. Deploy by digest only and verify deployed digest.

```bash
# Deploy by digest
python manage.py modalctl deploy --ref ns/name@ver --env dev --oci ghcr.io/...@sha256:...

# Verify bound digest matches expected
python manage.py modalctl verify-digest --ref ns/name@ver --env dev --oci ghcr.io/...@sha256:...

# Status / logs
python manage.py modalctl status --ref ns/name@ver --env dev
python manage.py modalctl logs --ref ns/name@ver --env dev

# Sync required secrets (names from registry.yaml)
python manage.py modalctl sync-secrets --ref ns/name@ver --env staging --fail-on-missing
```
