# CLI Reference

Command-line interfaces for processor execution and Modal deployment.

## run_processor

Execute processors across different adapters with unified interface.

### Basic Usage

```bash
python manage.py run_processor \
  --ref llm/litellm@1 \
  --adapter modal \
  --write-prefix /artifacts/outputs/text/ \
  --inputs-json '{"messages":[{"role":"user","content":"Hello"}]}' \
  --json
```

- `--ref` (required): Processor reference in format `{namespace}/{name}@{version}` (e.g., `llm/litellm@1`)
- `--adapter` (required): Adapter to use (`local` or `modal`)
- `--mode` (optional): Execution mode (`default` or `smoke`); smoke mode stays hermetic and skips Docker networks/artifact store
- `--write-prefix` (required): WorldPath prefix for outputs (must end with `/`)
- `--inputs-json` (required): JSON string containing processor inputs
- `--adapter-opts-json` (optional): JSON string with adapter-specific options
- `--json` (optional): Output canonical envelope instead of just index path

### Output Modes

**Without `--json`** (default):
```
/artifacts/execution/E123/outputs.json
```

**With `--json`**:
```json
{
  "status": "success",
  "execution_id": "E123",
  "outputs": [
    {
      "path": "/artifacts/outputs/text/response.txt",
      "cid": "b3:abc123...",
      "size_bytes": 42,
      "mime": "text/plain"
    }
  ],
  "index_path": "/artifacts/execution/E123/outputs.json",
  "meta": {
    "image_digest": "ghcr.io/veyorokon/llm_litellm@sha256:...",
    "env_fingerprint": "adapter=modal,image_digest=...,cpu=1,memory_gb=2,timeout_s=60,snapshot=off,present_env_keys=[OPENAI_API_KEY]",
    "duration_ms": 1234
  }
}
```

### Adapter Options

**Local adapter:**
```bash
--adapter-opts-json '{"timeout_s": 120}'
```

**Modal adapter:**
```bash
--adapter-opts-json '{"timeout_s": 120}'
```

### Smoke Mode

Smoke mode replaces the legacy mock adapter. Provide `--mode smoke` (or include `{"mode":"smoke"}` in the inputs) to force deterministic mock outputs without requiring Docker, MinIO, or provider credentials. This is the mode the smoke tests and acceptance suite rely on.

### Examples

**Local execution:**
```bash
python manage.py run_processor \
  --ref llm/litellm@1 \
  --adapter local \
  --write-prefix /artifacts/outputs/text/ \
  --inputs-json '{"messages":[{"role":"user","content":"Explain quantum computing"}], "model": "openai/gpt-4o-mini"}'
```

**Modal execution with timeout:**
```bash
python manage.py run_processor \
  --ref llm/litellm@1 \
  --adapter modal \
  --write-prefix /artifacts/outputs/text/ \
  --inputs-json '{"messages":[{"role":"user","content":"Generate a story"}]}' \
  --adapter-opts-json '{"timeout_s": 300}' \
  --json
```

**Smoke execution for testing:**
```bash
python manage.py run_processor \
  --ref llm/litellm@1 \
  --adapter local \
  --mode smoke \
  --write-prefix /artifacts/outputs/text/ \
  --inputs-json '{"messages":[{"role":"user","content":"Test"}]}' \
  --json
```

## sync_modal

Deploy Modal functions from the committed module.

### Why Pre-deploy?

Modal functions must be defined at import time for warm starts and snapshots. We deploy a deterministic function per processor ref.

### Basic Usage

```bash
python manage.py sync_modal --env dev
```

This runs:
```bash
modal deploy --env dev -m modal_app
```

The module is parameterized entirely by environment variables:
- `PROCESSOR_REF` — e.g., `llm/litellm@1`
- `IMAGE_REF` — digest-pinned OCI image
- `TIMEOUT_S`, `CPU`, `MEMORY_MIB`, `GPU` — resource profile
- `TOOL_SECRETS` — comma-separated tool secret names (e.g., `OPENAI_API_KEY`)
- `MODAL_APP_NAME` — app name (default `theory-rt`)

### Parameters

- `--env` (required): Modal environment (`dev`, `staging`, `main`)

### Secrets

Create once per environment:
```bash
modal secret create REGISTRY_AUTH \
  REGISTRY_USERNAME="$GITHUB_USERNAME" \
  REGISTRY_PASSWORD="$GITHUB_PAT"

modal secret create OPENAI_API_KEY OPENAI_API_KEY="$OPENAI_API_KEY"
```

### Troubleshooting

**Unauthorized image pulls:** Fix `REGISTRY_AUTH` in target environment.

**Function not found:** Ensure deployment ran for the specific environment (`--env`), and `PROCESSOR_REF`/`IMAGE_REF` are set.
