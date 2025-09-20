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
  "index_path": "/artifacts/execution/exec_abc123/outputs.json",
  "meta": {
    "image_digest": "sha256:abc123...",
    "mode": "mock",
    "duration_ms": 2341
  }
}
```

## CLI Access

```bash
# Get canonical outputs in mock mode (no Docker)
python manage.py run_processor \
  --ref llm/litellm@1 \
  --adapter local \
  --mode mock \
  --inputs-json '{"schema":"v1","params":{"messages":[{"role":"user","content":"Hello"}]}}' \
  --json
```

## Implementation Notes

- Local adapter supports `mode=mock` and `mode=real`; Modal adapter always runs real mode but smoke tests force the inputs to `mode=mock`.
- Envelopes remain the same regardless of mode; only the meta fields differ (e.g., `mode` or resource usage).
- Output paths are canonicalized, deduplicated, and sorted.
