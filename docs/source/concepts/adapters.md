# Adapters & Placement

Adapters provide uniform processor execution across different compute environments while maintaining consistent APIs and envelope formats.

## Adapter Types

### Local Adapter

Executes processors on the host. In **mode="real"** it launches Docker containers and writes via ArtifactStore; in **mode="mock"** it fabricates deterministic outputs under the requested write prefix without external dependencies.

**Use cases:**
- Development and CI smoke tests (`mode=mock`)
- Integration testing with real containers (`mode=real`)
- On-premise deployments

**Characteristics:**
- Same envelope format for both modes
- Docker isolation only in real mode
- No MinIO or Docker required in mock mode

### Modal Adapter

Executes processors on Modal's serverless platform with pre-deployed functions.

**Use cases:**
- Production workloads
- GPU-intensive processors
- Scalable execution with warm pools

**Characteristics:**
- Uses pinned `image.oci` digests from registry
- Secrets mounted by name via Modal Secret Store
- Identical envelope format to local adapter

## Uniform Adapter API

All adapters implement the same keyword-only `invoke` signature:

```python
def invoke(
    *,
    processor_ref: str,
    inputs_json: dict,
    write_prefix: str,
    execution_id: str,
    registry_snapshot: dict,
    adapter_opts: dict,
    secrets_present: list[str],
) -> dict:
    ...
```

### Key Points

- `inputs_json` now carries `mode` (`"mock"` or `"real"`). Adapters do not infer from environment variables.
- `secrets_present` contains **names only**; adapters never receive secret values.
- Envelopes are identical across adapters; mock vs real affects only IO side effects.

## Implementation Details

### Local Adapter

- Real mode pulls/builds the pinned image and runs it via Docker.
- Mock mode bypasses Docker/ArtifactStore and writes outputs directly in-process.
- Both modes emit identical success/error envelopes; only the IO path differs.

### Modal Adapter

- Uses `modal deploy -m modal_app.py` and `ModalAdapter` runtime.
- Relies on Modal secrets (`REGISTRY_AUTH`, etc.) for image pulls.
- Assumes inputs already specify `mode`; Modal functions typically force `mode="mock"` in smoke tests.

## Adapter Selection

Choose adapter and mode explicitly:

```bash
# Local mock run (no external deps)
python manage.py run_processor --adapter local --mode mock --ref llm/litellm@1 ...

# Local real run (Docker)
python manage.py run_processor --adapter local --mode real --ref llm/litellm@1 ...

# Modal run (always real mode after deploy)
python manage.py run_processor --adapter modal --mode real --ref llm/litellm@1 ...
```

## Error Handling

Common error codes returned in envelopes:

- `ERR_MISSING_SECRET` – required secret absent
- `ERR_OUTPUT_DUPLICATE` – duplicate paths after canonicalization
- `ERR_IMAGE_PULL` – Docker pull failure (real mode)
- `ERR_TIMEOUT` – execution exceeded runtime limit
- `ERR_FUNCTION_NOT_FOUND` – Modal function missing

## Best Practices

### Development

1. Start with `mode=mock` for quick feedback.
2. Switch to `mode=real` on local adapter to validate Docker builds.
3. Deploy to Modal once registry digests are pinned.

### Testing

- Use `mode=mock` for deterministic unit tests.
- Use `mode=real` for integration tests requiring containers/MinIO.
- Make sure tests explicitly set `mode`; no environment heuristics remain.

### Security

- Never log secret values.
- Environment fingerprints should list only secret names.
- Modal deploy workflow syncs secrets before running real mode.
