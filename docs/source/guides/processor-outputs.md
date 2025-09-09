# Processor Outputs

Processor execution generates canonical outputs in a standardized JSON envelope format. This ensures consistent output handling across all adapters (local, mock, modal) and provides deterministic artifact management.

## Canonical Output Format

Successful processor execution returns:

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
    },
    {
      "path": "/artifacts/outputs/meta.json", 
      "cid": "b3:789abc...",
      "size_bytes": 198,
      "mime": "application/json"
    }
  ],
  "index_path": "/artifacts/execution/exec_abc123/outputs.json",
  "meta": {
    "image_digest": "sha256:abc123...",
    "env_fingerprint": "linux_x64_py311_openai",
    "duration_ms": 2341
  }
}
```

## Field Specifications

### Required Fields

- **status**: Execution status (`"success"` or `"error"`)
- **execution_id**: Unique execution identifier
- **outputs**: Array of output file descriptors
- **index_path**: Path to the outputs index artifact

### Output Descriptors

Each output in the `outputs` array contains:

- **path**: Canonical world path (after canonicalization and deduplication)
- **cid**: Content identifier (BLAKE3 hash with `b3:` prefix)
- **size_bytes**: File size in bytes
- **mime**: MIME type (detected or inferred)

### Meta Object

The `meta` object contains adapter-specific metadata:

- **image_digest**: Container image digest (local/modal adapters)
- **env_fingerprint**: Environment specification for reproducibility
- **duration_ms**: Execution duration in milliseconds
- **tokens_in/tokens_out**: Token usage for LLM processors
- **model**: Model name for LLM processors

## Path Canonicalization

Outputs undergo path canonicalization to prevent duplicates and ensure deterministic ordering:

1. **Prefix Resolution**: Apply write prefix to relative paths
2. **Canonicalization**: Use `canon_path_facet_root()` for consistent formatting  
3. **Duplicate Detection**: Reject executions with duplicate target paths
4. **Lexicographic Ordering**: Sort outputs by canonical path

## Index Artifact

The index artifact at `/artifacts/execution/<id>/outputs.json` contains the complete outputs array in JSON Canonical Serialization (JCS) format:

```json
[
  {
    "cid": "b3:def456...",
    "mime": "text/plain", 
    "path": "/artifacts/outputs/text/response.txt",
    "size_bytes": 1247
  },
  {
    "cid": "b3:789abc...",
    "mime": "application/json",
    "path": "/artifacts/outputs/meta.json", 
    "size_bytes": 198
  }
]
```

This provides a deterministic, cryptographically verifiable record of execution outputs.

## Error Format

Failed executions return:

```json
{
  "status": "error",
  "execution_id": "exec_def789",
  "error": {
    "code": "container_failed",
    "message": "Container exited with code 1", 
    "details": {
      "exit_code": 1,
      "stderr": "Process failed: invalid input"
    }
  }
}
```

## Usage Examples

### CLI Access

```bash
# Get canonical outputs with --json flag
python manage.py run_processor \
  --ref llm/litellm@1 \
  --adapter mock \
  --inputs-json '{"messages":[{"role":"user","content":"Hello"}]}' \
  --json
```

### Save Outputs Locally

```bash
# Save all outputs to directory
python manage.py run_processor \
  --ref llm/litellm@1 \
  --adapter local \
  --save-dir ./experiment-outputs \
  --inputs-json '{"messages":[{"role":"user","content":"Test"}]}'

# Save first output only
python manage.py run_processor \
  --ref llm/litellm@1 \
  --adapter local \
  --save-first ./response.txt \
  --inputs-json '{"messages":[{"role":"user","content":"Test"}]}'
```

## Implementation Notes

- All adapters (local, mock, modal) generate canonical outputs
- Modal adapter canonical parity scheduled for 0022
- Path canonicalization prevents write conflicts
- Index artifacts enable deterministic replay and verification
- CID computation uses BLAKE3 for performance and security