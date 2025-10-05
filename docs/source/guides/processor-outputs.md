# Processor Outputs

Processor execution generates canonical outputs in a standardized envelope format. The envelope is identical whether the processor runs in `mode="mock"` (hermetic) or `mode="real"` (full execution).

## Canonical Output Format

```json
{
  "status": "success",
  "execution_id": "exec_abc123",
  "outputs": [
    {
      "path": "/artifacts/outputs/text/response.txt",
      "cid": "b3:def456...",
      "size_bytes": 1247,
      "mime": "text/plain"
    }
  ],
  "index_path": "/artifacts/outputs/.../exec_abc123/outputs.json",
  "meta": {
    "image_digest": "ghcr.io/...@sha256:abc123...",
    "mode": "mock",
    "duration_ms": 2341
  }
}
```

## CLI Access

```bash
# Start local container
OPENAI_API_KEY=$OPENAI_API_KEY python manage.py localctl start --ref llm/litellm@1

# Get canonical outputs in mock mode
python manage.py localctl run \
  --ref llm/litellm@1 \
  --mode mock \
  --inputs-json '{"schema":"v1","params":{"messages":[{"role":"user","content":"Hello"}]}}' \
  --json
```

## Implementation Notes

- Both adapters honour `mode=mock` and `mode=real`; smoke tests simply pass `mode=mock` through the same execution surface.
- Envelopes remain the same regardless of mode; only the meta fields differ (e.g., `mode` or resource usage).
- Output paths are canonicalized, deduplicated, and sorted.
