# CLI Reference

Command-line interfaces for processor execution and Modal deployment.

## run_processor

Execute processors across adapters with explicit mode selection.

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
- `--write-prefix` (optional): Output prefix (default `/artifacts/outputs/`). Must include `{execution_id}` to prevent collisions.
- `--inputs-json` (optional): JSON payload (schema v1)
- `--adapter-opts-json` (optional): Adapter-specific options
- `--plan`, `--attach`, `--json`, `--save-dir`, `--save-first`: unchanged

> The legacy `--adapter mock` shim has been removed. Use `--mode mock` with the local adapter instead.

### Mode Behaviour

| Mode | Effect |
|------|--------|
| `mock` | No Docker/MinIO or network calls; deterministic outputs |
| `real` | Full container execution (or Modal remote) with real provider calls |

### Image Selection (`--build`)

The `--build` flag affects only the local adapter:

- `local + --build=true` → use the newest locally built, timestamped tag (build-from-source loop)
- `local + --build=false` (default) → use the pinned registry digest from the per-processor `registry.yaml`
- `modal + --build=any` → ignored; the adapter performs an SDK lookup of the deployed HTTP app/function (deployment is pinned by digest)

Example:

```bash
# Build-from-source loop (local only)
python manage.py run_processor --ref ns/name@1 --adapter local --mode mock --build --json

# Pinned digest (supply-chain parity)
python manage.py run_processor --ref ns/name@1 --adapter local --mode mock --json

# Modal ignores --build
python manage.py run_processor --ref ns/name@1 --adapter modal --mode mock --json
```

### Examples

```bash
# Local mock run (fast smoke test)
python manage.py run_processor --ref llm/litellm@1 --adapter local --mode mock --json

# Local real run (Docker)
python manage.py run_processor --ref llm/litellm@1 --adapter local --mode real

# Modal real run
python manage.py run_processor --ref llm/litellm@1 --adapter modal --mode real --json

# Envelopes are returned by the HTTP response; use --json to pretty-print in CLI context
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
