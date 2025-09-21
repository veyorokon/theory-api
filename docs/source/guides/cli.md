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

### Examples

```bash
# Local mock run (fast smoke test)
python manage.py run_processor --ref llm/litellm@1 --adapter local --mode mock --json

# Local real run (Docker)
python manage.py run_processor --ref llm/litellm@1 --adapter local --mode real

# Modal real run
python manage.py run_processor --ref llm/litellm@1 --adapter modal --mode real --json

# Capture stdout only (machine-readable envelope); logs stream to stderr automatically when --json is set.
python manage.py run_processor ... --json 1>result.json 2>logs.ndjson
```

## sync_modal_secrets

Idempotently ensures all registry-declared secrets exist in the Modal environment. Uses GitHub secrets as the source of truth.
