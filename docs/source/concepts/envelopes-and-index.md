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
  "index_path": "/artifacts/execution/E123/outputs.json",
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

Modal deploy workflows force `mode="mock"` for their smoke tests, but the resulting envelope is identical.

## Index Artifacts

The `index_path` points to a JSON artifact containing the outputs array. Structure:

```json
{
  "outputs": [
    {
      "path": "/artifacts/outputs/text/response.txt",
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

- `ERR_MISSING_SECRET`
- `ERR_OUTPUT_DUPLICATE`
- `ERR_TIMEOUT`
- `ERR_IMAGE_PULL`
- `ERR_FUNCTION_NOT_FOUND`

## CLI Output

```bash
# Default (path only)
$ python manage.py run_processor --ref ... --adapter local --mode mock
/artifacts/execution/E123/outputs.json

# With --json
$ python manage.py run_processor --ref ... --adapter local --mode real --json
{"status":"success", ... }
```
