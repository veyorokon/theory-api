(run-processor)=
# Run Processor

Unified processor execution with support for multiple adapters (local, mock, Modal), attachment materialization, and artifact rewriting.

## Quick Start

### Mock Adapter (No Setup Required)

Run a processor using the mock adapter:

```bash
cd theory_api/code && python manage.py run_processor --ref llm/litellm@1 --adapter mock --inputs-json '{"messages":[{"role":"user","content":"Hello!"}]}'
```

**Expected Output:**
```json
{
  "status": "success",
  "execution_id": "abc123",
  "outputs": [
    {
      "path": "/artifacts/outputs/text/response.txt",
      "cid": "b3:def456...",
      "size_bytes": 26,
      "mime": "text/plain"
    },
    {
      "path": "/artifacts/outputs/meta.json",
      "cid": "b3:789abc...", 
      "size_bytes": 145,
      "mime": "application/json"
    }
  ],
  "index_path": "/artifacts/execution/abc123/outputs.json",
  "meta": {
    "model": "mock-llm",
    "tokens_in": 1,
    "tokens_out": 5,
    "duration_ms": 100
  }
}
```

### Local Adapter (Docker Execution)

Run a processor locally using Docker containers:

```bash
# Requires Docker installed and running
cd theory_api/code && python manage.py run_processor --ref llm/litellm@1 --adapter local --inputs-json '{"messages":[{"role":"user","content":"Hello!"}]}'
```

**Prerequisites:**
- Docker installed and running
- Processor image available (built from Dockerfile or pulled from registry)

**Expected Output:**
```json
{
  "status": "success",
  "execution_id": "def789",
  "outputs": [
    {
      "path": "/artifacts/outputs/text/response.txt",
      "cid": "b3:123def...",
      "size_bytes": 1247,
      "mime": "text/plain"
    },
    {
      "path": "/artifacts/outputs/meta.json",
      "cid": "b3:456abc...",
      "size_bytes": 198,
      "mime": "application/json"
    }
  ],
  "index_path": "/artifacts/execution/def789/outputs.json",
  "meta": {
    "image_digest": "sha256:abc123...",
    "env_fingerprint": "linux_x64_py311_openai",
    "duration_ms": 2341
  }
}
```

### Modal Adapter (Cloud Execution)

With Modal token configured and `MODAL_ENABLED=True`:

```bash
export MODAL_TOKEN_ID="your-token"
export MODAL_TOKEN_SECRET="your-secret"
export OPENAI_API_KEY="your-key"
export MODAL_ENABLED=True
cd theory_api/code && python manage.py run_processor --ref llm/litellm@1 --adapter modal --inputs-json '{"messages":[{"role":"user","content":"Hello!"}]}'
```

**Note:** Full canonical outputs parity for Modal adapter will land in 0022. Safe to run mock/local adapters now for canonical envelope testing.

## Attachments

The run_processor command supports file attachments that are automatically materialized and rewritten:

```bash
# Attach an image file
python manage.py run_processor \
  --ref llm/litellm@1 \
  --adapter mock \
  --attach image=photo.jpg \
  --inputs-json '{"messages":[{"content":[{"$attach":"image"}]}]}'
```

The `$attach` reference is automatically rewritten to:
```json
{
  "$artifact": "/artifacts/inputs/<cid>/photo.jpg",
  "cid": "b3:abc123...",
  "mime": "image/jpeg"
}
```

## Command Options

```bash
python manage.py run_processor [options]
```

**Required:**
- `--ref`: Processor reference (e.g., `llm/litellm@1`)

**Optional:**
- `--adapter`: Execution adapter (`local`, `mock`, `modal`) - default: `local`
  - `local`: Docker container execution (requires Docker)
  - `mock`: Simulated execution for testing/CI
  - `modal`: Cloud execution via Modal platform
- `--plan`: Plan key for budget tracking
- `--write-prefix`: Output prefix path (must end with `/`) - default: `/artifacts/outputs/`
- `--inputs-json`: JSON input for processor - default: `{}`
- `--adapter-opts-json`: Adapter-specific options as JSON
- `--attach name=path`: Attach file (can be used multiple times)
- `--json`: Output JSON response
- `--save-dir`: Save outputs to local directory
- `--save-first`: Save only first output to local directory
- `--stream`: Stream output *(future: 0022)*

## Examples

### Basic LLM Processing

```bash
# Using mock adapter (fast, no dependencies)
python manage.py run_processor \
  --ref llm/litellm@1 \
  --adapter mock \
  --inputs-json '{"messages":[{"role":"user","content":"What is Theory?"}]}' \
  --json

# Using local Docker adapter  
python manage.py run_processor \
  --ref llm/litellm@1 \
  --adapter local \
  --inputs-json '{"messages":[{"role":"user","content":"What is Theory?"}]}' \
  --json
```

### With Budget Tracking

```bash
python manage.py run_processor \
  --ref llm/litellm@1 \
  --adapter mock \
  --plan my-plan \
  --inputs-json '{"messages":[{"role":"user","content":"Hello"}]}'
```

### Multiple Attachments

```bash
python manage.py run_processor \
  --ref llm/litellm@1 \
  --adapter mock \
  --attach doc1=report.pdf \
  --attach doc2=data.csv \
  --inputs-json '{"messages":[{"content":[{"$attach":"doc1"},{"$attach":"doc2"}]}]}'
```

### Custom Write Prefix

```bash
python manage.py run_processor \
  --ref llm/litellm@1 \
  --adapter mock \
  --write-prefix /artifacts/outputs/experiment-1/ \
  --inputs-json '{"messages":[{"role":"user","content":"Test"}]}'
```

### Save Outputs Locally

```bash
# Save all outputs to local directory
python manage.py run_processor \
  --ref llm/litellm@1 \
  --adapter mock \
  --save-dir ./outputs \
  --inputs-json '{"messages":[{"role":"user","content":"Hello"}]}'

# Save only first output to local directory  
python manage.py run_processor \
  --ref llm/litellm@1 \
  --adapter mock \
  --save-first ./first-output.txt \
  --inputs-json '{"messages":[{"role":"user","content":"Hello"}]}'
```

## Processor Registry

Processors are defined in YAML registry files under `code/apps/core/registry/processors/`. Each processor specifies:

- **image**: Container image or Dockerfile path
- **runtime**: CPU, memory, timeout, GPU requirements
- **adapter**: Adapter-specific configuration
- **secrets**: Required secret names (resolved at runtime)
- **inputs/outputs**: Schema definitions

Example registry entry:
```yaml
ref: llm/litellm@1
description: LLM processor using LiteLLM
image:
  dockerfile: apps/core/processors/llm_litellm/Dockerfile
runtime:
  cpu: 1
  memory: 512
  timeout: 300
adapter:
  modal:
    stub_name: llm_litellm_v1
secrets:
  - OPENAI_API_KEY
```

## Determinism & Receipts

Each successful execution generates a determinism receipt at `/artifacts/execution/<id>/determinism.json` containing:
- `seed`: Execution seed for reproducibility
- `memo_key`: Cache key for memoization
- `env_fingerprint`: Environment specification
- `output_cids`: Content identifiers of outputs

## Troubleshooting

### Docker Not Available (Local Adapter)
```
Error: Docker daemon not running or not installed
```
Solution: Install Docker and ensure Docker daemon is running. Use `mock` adapter for Docker-free testing.

### Container Image Not Found
```
Error: Unable to find image 'docker.io/library/python:3.11-slim'
```
Solution: Pull the required image (`docker pull python:3.11-slim`) or build from Dockerfile.

### Modal Not Available
```
Error: Modal not available. Install 'modal' package and set MODAL_ENABLED=True
```
Solution: Install modal (`pip install modal`) and set `MODAL_ENABLED=True` in settings.

### Invalid Write Prefix
```
Error: --write-prefix must end with /
```
Solution: Ensure write prefix ends with slash (e.g., `/artifacts/outputs/`)

### Attachment Not Found
```
Attachment file not found: path/to/file
```
Solution: Verify file path exists and is accessible.

## Architecture

The run_processor command implements:
1. **Attachment materialization**: Files uploaded to `/artifacts/inputs/<cid>/`
2. **Reference rewriting**: `$attach` → `$artifact` transformation
3. **Adapter abstraction**: Pluggable execution backends
4. **Budget tracking**: Integration with Plan/Execution models
5. **Determinism receipts**: Reproducibility metadata