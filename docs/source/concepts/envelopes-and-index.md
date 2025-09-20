# Envelopes & Index Artifacts

Execution results are returned in standardized envelope formats with accompanying index artifacts for output discovery.

## Envelope Formats

All adapters return consistent envelope structures regardless of execution environment.

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
    "env_fingerprint": "adapter=modal,image_digest=...,cpu=1,memory_gb=2,timeout_s=60,snapshot=off,present_env_keys=[OPENAI_API_KEY]",
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
    "env_fingerprint": "adapter=local,env_keys_present=[]"
  }
}
```

## Envelope Fields

### Common Fields

- **`status`**: Either `"success"` or `"error"`
- **`execution_id`**: Unique identifier for this execution
- **`meta`**: Metadata about execution environment and performance

### Success-Specific Fields

- **`outputs`**: Array of output artifacts with metadata
- **`index_path`**: WorldPath to the outputs index artifact
- **`seed`** (optional): Random seed used for deterministic execution
- **`memo_key`** (optional): Key for memoization and caching

### Error-Specific Fields

- **`error`**: Error details with structured code and message
  - **`code`**: Standardized error code (e.g., `ERR_MISSING_SECRET`)
  - **`message`**: Human-readable error description

## Output Metadata Structure

Each output in the `outputs` array contains:

```json
{
  "path": "/artifacts/outputs/text/response.txt",
  "cid": "b3:abc123...",
  "size_bytes": 42,
  "mime": "text/plain"
}
```

### Output Fields

- **`path`**: Canonical WorldPath to the artifact
- **`cid`**: Content identifier for content-addressable retrieval
- **`size_bytes`**: Size of the artifact in bytes
- **`mime`**: MIME type for proper content handling

## Index Artifacts

The `index_path` points to a JSON artifact containing the outputs array for convenient discovery:

### Index Structure

```json
{
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
  ]
}
```

### Index Properties

- **Object wrapper**: Always wrapped in `{"outputs": [...]}` structure
- **Compact JSON**: No unnecessary whitespace for efficiency
- **UTF-8 encoding**: Consistent character encoding
- **Sorted paths**: Outputs sorted by path for deterministic ordering

## Environment Fingerprinting

The `env_fingerprint` field captures execution environment details without exposing sensitive data:

### Format

```
adapter=modal,image_digest=...,cpu=1,memory_gb=2,timeout_s=60,snapshot=off,present_env_keys=[OPENAI_API_KEY]
```

### Components

- **`adapter`**: Execution adapter used (`local` or `modal`)
- **`image_digest`**, **`cpu`**, **`memory_gb`**, **`timeout_s`**, **`snapshot`**: Normalized runtime settings
- **`present_env_keys`**: Sorted list of environment variable names present (names only, never values)
- **Additional fields**: Adapter-specific metadata

### Security

**Critical**: Environment fingerprinting records only **names** of environment variables, never their values.

## Error Codes

Standardized error codes for consistent error handling:

### Common Error Codes

- **`ERR_MISSING_SECRET`**: Required secret not available in environment
- **`ERR_OUTPUT_DUPLICATE`**: Duplicate output paths after canonicalization
- **`ERR_TIMEOUT`**: Execution exceeded configured timeout
- **`ERR_IMAGE_PULL`**: Failed to pull processor container image
- **`ERR_FUNCTION_NOT_FOUND`**: Modal function not deployed (Modal adapter only)
- **`ERR_ADAPTER_SIGNATURE`**: Adapter doesn't implement required interface
- **`ERR_RUN_PROCESSOR`**: General processor execution failure

### WorldPath Error Codes

- **`ERR_INVALID_WORLDPATH`**: Path violates canonicalization rules
- **`ERR_DECODED_SLASH`**: Path contains decoded `/` character
- **`ERR_DOT_SEGMENTS`**: Path contains `.` or `..` segments
- **`ERR_BAD_FACET`**: Invalid facet root in path
- **`ERR_SELECTOR_KIND_MISMATCH`**: Incorrect prefix/exact selector format

## Adapter Consistency

Both adapters (local and modal) implement the same envelope format. The local adapter supports two **modes**: default (Docker-backed) and smoke (hermetic mock). Both modes emit identical envelopes apart from metadata fields.

### Local Adapter

- **Object wrapper**: Creates `{"outputs": [...]}` index structure
- **Smoke vs default**: Smoke mode synthesizes outputs locally; default uses Docker + artifact store
- **Parity with Modal**: Same envelope format and error handling

### Modal Adapter

- **Pre-deployed functions**: No runtime decorators, consistent envelope format
- **Registry authentication**: Uses `REGISTRY_AUTH` for image pulls
- **Runtime secrets**: Mounted by name, recorded in environment fingerprint

## Usage Examples

### CLI Output

**Without `--json` flag** (default):
```bash
$ python manage.py run_processor --ref llm/litellm@1 --adapter modal --write-prefix /artifacts/outputs/text/ --inputs-json '{"messages":[{"role":"user","content":"Hello"}]}'
/artifacts/execution/E123/outputs.json
```

**With `--json` flag**:
```bash
$ python manage.py run_processor --ref llm/litellm@1 --adapter modal --write-prefix /artifacts/outputs/text/ --inputs-json '{"messages":[{"role":"user","content":"Hello"}]}' --json
{"status":"success","execution_id":"E123","outputs":[{"path":"/artifacts/outputs/text/response.txt","cid":"b3:abc123...","size_bytes":42,"mime":"text/plain"}],"index_path":"/artifacts/execution/E123/outputs.json","meta":{"image_digest":"ghcr.io/veyorokon/llm_litellm@sha256:...","env_fingerprint":"adapter=modal,env_keys_present=[OPENAI_API_KEY],modal_env=dev","duration_ms":1234}}
```

### Programmatic Usage

```python
from apps.core.adapters.modal_adapter import ModalAdapter

adapter = ModalAdapter()
result = adapter.invoke(
    processor_ref="llm/litellm@1",
    inputs_json={"messages": [{"role": "user", "content": "Hello"}]},
    write_prefix="/artifacts/outputs/text/",
    execution_id="E123",
    registry_snapshot=registry_snapshot,
    adapter_opts={},
    secrets_present=["OPENAI_API_KEY"]
)

if result["status"] == "success":
    # Access outputs
    for output in result["outputs"]:
        print(f"Output: {output['path']} (CID: {output['cid']})")

    # Access index
    index_path = result["index_path"]
    print(f"Index available at: {index_path}")
else:
    # Handle error
    error = result["error"]
    print(f"Error {error['code']}: {error['message']}")
```

## Settlement Integration

Successful executions include additional metadata for ledger settlement:

### Settlement Addenda

When outputs are present, the settlement process adds:

```json
{
  "outputs_index": "/artifacts/execution/E123/outputs.json",
  "outputs_count": 2
}
```

### Memo Hits

For memoized executions:
- **No reserve**: Budget not reserved for memo hits
- **Emit sequence**: `execution.memo_hit` → `execution.settle.success(actual=0, refund=0)`
- **Same envelope**: Consistent envelope format regardless of memo status

## Cross-References

- {doc}`worldpath` - WorldPath canonicalization rules for output paths
- {doc}`adapters` - Adapter implementations that produce envelopes
- {doc}`../apps/storage` - Storage layer for artifact retrieval
- [Local Adapter Docker Execution ADR](../adr/ADR-0015-local-adapter-docker-execution.md) - Local adapter envelope implementation
