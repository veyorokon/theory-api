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
```
Processor completed successfully
Outputs: {
  "/artifacts/outputs/text/response.txt": "Mock response to 1 messages",
  "/artifacts/outputs/metadata.json": "{...}"
}
```

### Modal Adapter (Cloud Execution)

With Modal token configured:

```bash
export MODAL_TOKEN_ID="your-token"
export OPENAI_API_KEY="your-key"
cd theory_api/code && python manage.py run_processor --ref llm/litellm@1 --adapter modal --inputs-json '{"messages":[{"role":"user","content":"Hello!"}]}'
```

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
- `--plan`: Plan key for budget tracking
- `--write-prefix`: Output prefix path (must end with `/`) - default: `/artifacts/outputs/`
- `--inputs-json`: JSON input for processor - default: `{}`
- `--adapter-opts-json`: Adapter-specific options as JSON
- `--attach name=path`: Attach file (can be used multiple times)
- `--json`: Output JSON response
- `--stream`: Stream output (if supported)

## Examples

### Basic LLM Processing

```bash
python manage.py run_processor \
  --ref llm/litellm@1 \
  --adapter mock \
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