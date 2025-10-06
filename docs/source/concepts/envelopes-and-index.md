# Envelopes & Index Artifacts

Execution results are returned in standardized envelope formats with accompanying index artifacts for output discovery.

## Envelope Formats

All adapters return consistent envelope structures regardless of execution environment. `mode` selects the IO path (mock vs real) but does not change the envelope shape.

### Success Envelope

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
    },
    {
      "path": "/artifacts/outputs/metadata.json",
      "cid": "b3:def456...",
      "size_bytes": 89,
      "mime": "application/json"
    }
  ],
  "index_path": "/artifacts/outputs/.../E123/outputs.json",
  "meta": {
    "image_digest": "ghcr.io/owner/llm_litellm@sha256:...",
    "env_fingerprint": "adapter=local,mode=mock,present_env_keys=[OPENAI_API_KEY]",
    "duration_ms": 1234
  }
}
```

### Error Envelope

```json
{
  "status": "error",
  "execution_id": "E124",
  "error": {
    "code": "ERR_MISSING_SECRET",
    "message": "Required secret OPENAI_API_KEY is missing"
  },
  "meta": {
    "env_fingerprint": "adapter=local,mode=real,env_keys_present=[]"
  }
}
```

## Environment Fingerprinting

The `env_fingerprint` field captures execution context without exposing secret values:

- `adapter`: `local` or `modal`
- `mode`: `mock` or `real`
- `image_digest`, `cpu`, `memory_gb`, `timeout_s`
- `present_env_keys`: sorted list of secret names

Static data only—no secret values.

## Adapter Consistency

Both adapters (local and modal) emit the same envelope format. The local adapter supports two modes:

- **mode="mock"** – Hermetic; writes outputs locally without Docker/ArtifactStore.
- **mode="real"** – Uses Docker and ArtifactStore (or Modal runtime) to persist artifacts.

Modal deploy workflows run `modalctl run --mode mock` for smoke tests; the resulting envelope is identical.

## Index Artifacts

The `index_path` points to a JSON artifact containing the outputs array. Structure:

```json
{
  "outputs": [
    {
      "path": "/artifacts/outputs/.../E123/outputs/text/response.txt",
      "cid": "b3:abc123...",
      "size_bytes": 42,
      "mime": "text/plain"
    }
  ]
}
```

Properties:

- Wrapper object (`{"outputs": [...]}`)
- Compact JSON (no extra whitespace)
- UTF-8 encoding
- Sorted by path

## Error Codes

Common codes surfaced in envelopes:

- `ERR_INPUTS` – Invalid or malformed input payload
- `ERR_PROVIDER` – Provider/model API failure
- `ERR_UPLOAD_PLAN` – Missing or invalid presigned upload URLs
- `ERR_RUNTIME` – Unexpected runtime error in processor
- `ERR_MISSING_SECRET` – Required secret not provided
- `ERR_OUTPUT_DUPLICATE` – Duplicate output path detected
- `ERR_TIMEOUT` – Processor execution timeout
- `ERR_IMAGE_PULL` – Failed to pull container image
- `ERR_FUNCTION_NOT_FOUND` – Modal function not deployed

## Contract: Envelopes vs Exceptions

**Processors always return an envelope.** They never raise exceptions to the client.

### What Returns Error Envelopes

User/processor errors → `status="error"` envelope:
- Invalid inputs → `ERR_INPUTS`
- Provider failures → `ERR_PROVIDER`
- Upload issues → `ERR_UPLOAD_PLAN`
- Runtime errors → `ERR_RUNTIME`

### What Raises Exceptions

Only orchestration/transport failures raise:
- `WsError` – Connection timeout, protocol violation, bad frames
- `DriftError` – Image digest mismatch (supply chain security)
- `ToolRunnerError` – Missing secrets, registry issues, build failures

### Testing Guidance

```python
# ✅ Correct: Assert on envelope
env = invoke_processor("llm/litellm@1", inputs={"bad": "data"})
assert env["status"] == "error"
assert env["error"]["code"] == "ERR_INPUTS"

# ❌ Wrong: Expect exception for processor errors
with pytest.raises(Exception):  # NO - processor errors are envelopes
    invoke_processor("llm/litellm@1", inputs={"bad": "data"})

# ✅ Correct: Expect exception for orchestration failures
with pytest.raises(ToolRunnerError):
    invoke_processor("nonexistent/processor@1", inputs={...})
```

## CLI Output

```bash
# Local execution with JSON output
$ python manage.py localctl run --ref llm/litellm@1 --mode mock --json
{"status":"success", ... }

# Modal execution with JSON output
$ python manage.py modalctl run --ref llm/litellm@1 --mode mock --json
{"status":"success", ... }
```
