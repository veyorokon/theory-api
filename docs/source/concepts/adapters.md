# Adapters & Placement

Adapters provide uniform processor execution across different compute environments while maintaining consistent APIs and envelope formats.

## Adapter Types

### Local Adapter

Executes processors in local Docker containers using the host system.

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

### Mock Adapter

Provides deterministic test execution without external dependencies.

**Use cases:**
- Unit testing
- Integration test fixtures
- Development without real processor execution

**Characteristics:**
- Configurable outputs
- No external dependencies
- Deterministic execution

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
    "image_digest": "ghcr.io/veyorokon/llm_litellm@sha256:...",
    "env_fingerprint": "adapter=modal,env_keys_present=[OPENAI_API_KEY],modal_env=dev",
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

### Local/Mock Adapters

- **Object wrapper**: Creates `{"outputs": [...]}` index structure
- **Nested error envelopes**: Processor errors wrapped in adapter envelope
- **Parity with Modal**: Same envelope format and error handling

### Modal Adapter

- **Committed module**: Functions deployed from a single committed module via `sync_modal`/`modal deploy`
- **Deterministic naming**: One function per processor ref (`exec__{slug}__v{ver}`)
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

Adapters are selected via CLI `--adapter` parameter or programmatically:

```bash
# Local execution
python manage.py run_processor --adapter local --ref llm/litellm@1 ...

# Modal execution  
python manage.py run_processor --adapter modal --ref llm/litellm@1 ...

# Mock execution
python manage.py run_processor --adapter mock --ref llm/litellm@1 ...
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

**Mock:**
```json
{
  "outputs": [
    {"path": "response.txt", "content": "Mock response"},
    {"path": "metadata.json", "content": "{\"mock\": true}"}
  ]
}
```

### Environment Variables

- `MODAL_ENABLED`: Enable Modal adapter (Django settings)
- `MODAL_ENV`: Environment name for Modal app (`dev`, `staging`, `main`)
- `MODAL_APP_NAME`: Override default app name pattern

## Best Practices

### Development

1. Start with **local** adapter for initial development
2. Use **mock** adapter for unit tests
3. Switch to **modal** for production-like testing

### Production

1. Pre-deploy Modal functions with `sync_modal`
2. Use **modal** adapter for scalable execution
3. Monitor function cold start metrics

### Testing

1. Use **mock** adapter for deterministic tests
2. Use **local** adapter for integration tests
3. Validate envelope format consistency across adapters

### Security

1. Never log secret values in adapter code
2. Use `secrets_present` list for environment fingerprinting
3. Validate secret availability before execution
