# Adapters & Placement

Adapters provide uniform processor execution across different compute environments while maintaining consistent APIs and envelope formats.

## Adapter Types

### Local Adapter

Executes processors on the host. In **default mode** it uses Docker containers and artifact storage; in **smoke mode** it fabricates deterministic outputs without touching external services.

**Use cases:**
- Development and testing
- CI/CD environments with Docker
- On-premise deployments

**Characteristics:**
- Synchronous execution
- Docker-based isolation
- Host resource constraints apply

### Modal Adapter

Executes processors on Modal's serverless platform with pre-deployed functions.

**Use cases:**
- Production workloads
- GPU-intensive processors
- Scalable execution with warm pools

**Characteristics:**
- Pre-deployed functions for warm starts
- GPU and high-memory support
- Built-in secrets management
- Automatic scaling

### Smoke Mode (Local Adapter Fast Path)

Smoke mode replaces the legacy mock adapter. Supply `{"mode": "smoke"}` in inputs (or `--mode smoke` via CLI) to write mock artifacts directly under the requested prefix without Docker/MinIO/GHCR pulls.

## Uniform Adapter API

All adapters implement the same interface with keyword-only parameters:

```python
def invoke(
    *,
    processor_ref: str,
    inputs_json: dict,
    write_prefix: str,
    execution_id: str,
    registry_snapshot: dict,
    adapter_opts: dict,
    secrets_present: list[str]
) -> envelope
```

### Parameters

- **processor_ref**: Registry reference (e.g., `llm/litellm@1`)
- **inputs_json**: Processor input data as dictionary
- **write_prefix**: WorldPath prefix for outputs (must end with `/`)
- **execution_id**: Unique execution identifier
- **registry_snapshot**: Complete registry state at execution time
- **adapter_opts**: Adapter-specific configuration options
- **secrets_present**: List of available secret names (names only, never values)

### Return Value

All adapters return consistent **envelope** format:

**Success:**
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
    "image_digest": "ghcr.io/owner/llm_litellm@sha256:...",
    "env_fingerprint": "adapter=modal,image_digest=...,cpu=1,memory_gb=2,timeout_s=60,snapshot=off,present_env_keys=[OPENAI_API_KEY]",
    "duration_ms": 1234
  }
}
```

**Error:**
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

## Implementation Details

### Local Adapter Details

- **Object wrapper**: Creates `{"outputs": [...]}` index structure
- **Smoke vs default**: Smoke writes mock files; default launches Docker with the pinned image
- **Parity with Modal**: Same envelope format and error handling

### Modal Adapter

- **Committed module**: Functions deployed from a single committed module via `modal deploy -m modal_app` (no codegen)
- **Deterministic naming**: App `{slug}-v{ver}-{env}`; Function `run`
- **Registry auth**: Uses `REGISTRY_AUTH` secret for GHCR image pulls
- **Runtime secrets**: Mounted by name matching environment variables

### Secrets Handling

**Security principle**: Adapter receives only secret **names**, never values.

```python
# In env_fingerprint
"env_keys_present": ["OPENAI_API_KEY", "LITELLM_API_BASE"]  # Names only
```

**Modal secrets mounting:**
```python
secrets = [modal.Secret.from_name(name) for name in secrets_present]
```

**Registry authentication (special case):**
```python
image = modal.Image.from_registry(
    registry_snapshot['image']['oci'],
    secret=modal.Secret.from_name('REGISTRY_AUTH')
)
```

## Adapter Selection

Adapters are selected via CLI `--adapter` parameter or programmatically. Use `--mode smoke` to force the hermetic path.

```bash
# Local execution
python manage.py run_processor --adapter local --ref llm/litellm@1 ...

# Smoke execution (no external deps)
python manage.py run_processor --adapter local --mode smoke --ref llm/litellm@1 ...

# Modal execution
python manage.py run_processor --adapter modal --ref llm/litellm@1 ...
```

## Error Handling

### Common Error Codes

- `ERR_MISSING_SECRET`: Required secret not available
- `ERR_OUTPUT_DUPLICATE`: Duplicate output paths after canonicalization
- `ERR_TIMEOUT`: Execution exceeded timeout limit
- `ERR_IMAGE_PULL`: Failed to pull processor image
- `ERR_FUNCTION_NOT_FOUND`: Modal function not deployed (Modal only)

### Error Propagation

1. **Processor errors**: Wrapped in adapter envelope with `status: "error"`
2. **Adapter errors**: Direct envelope with error details
3. **System errors**: Logged and re-raised with context

## Configuration

### Adapter Options

**Local:**
```json
{"timeout_s": 120}
```

**Modal:**
```json
{"timeout_s": 300}
```

### Environment Variables

- `MODAL_ENABLED`: Enable Modal adapter (Django settings)
- `MODAL_ENV`: Environment name for Modal app (`dev`, `staging`, `main`)
- `MODAL_APP_NAME`: Override default app name pattern

## Best Practices

### Development

1. Start with **local --mode smoke** for initial development
2. Switch to **local default** for Docker parity
3. Use **modal** for production-like testing

### Production

1. Pre-deploy Modal functions with `sync_modal`
2. Use **modal** adapter for scalable execution
3. Monitor function cold start metrics

### Testing

1. Use **local --mode smoke** for deterministic tests
2. Use **local default** for integration tests requiring Docker
3. Validate envelope format consistency across adapters

### Security

1. Never log secret values in adapter code
2. Use `secrets_present` list for environment fingerprinting
3. Validate secret availability before execution
