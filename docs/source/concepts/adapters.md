# Adapters (HTTP transport-only)

Adapters move payloads to processors over HTTP and validate envelopes. They do no business logic.

## Types

### LocalAdapter (Docker → HTTP)

- Start container by pinned digest (select platform by host arch)
- Poll `GET /healthz`, then `POST /run` (optional: `/run-stream` for SSE if the processor implements streaming)
- Validate envelope; enforce index discipline; optional digest drift check

### ModalAdapter (Web endpoint → HTTP)

- Call deployed FastAPI endpoint bound to the pinned digest
- Same payload and envelope; enforce digest drift vs deployment

## Minimal API (Protocol)

```python
def invoke(
    *,
    ref: str,
    payload: dict,
    timeout_s: int,
    oci: str | None,
    stream: bool = False,
) -> dict | Iterator[dict]
```

Key points:
- `payload.mode ∈ {mock, real}`; adapters never infer from env
- In PR lane, use `mode=mock` (hermetic; no secrets)
- Envelopes identical across adapters; only transport differs

## Image Selection Behavior

The adapter chooses which image to run or call based on adapter type and the `--build` flag passed to `run_processor`:

| Adapter | `--build` | Behavior |
|---------|-----------|----------|
| local   | true      | Uses the newest locally built, timestamped tag (build-from-source loop) |
| local   | false     | Uses the pinned registry digest from the processor's `registry.yaml` |
| modal   | any       | Ignores `--build`; performs SDK lookup of the deployed app/function bound to the pinned digest |

Notes:
- “Pinned digest” comes from `code/apps/core/processors/<ns>_<name>/registry.yaml` (`image.platforms.{amd64,arm64}` and `default_platform`).
- Modal deployments must be created by digest; the adapter then looks up the deployed app and can perform a digest drift check.

## Selection examples

```bash
# Local mock (no external deps)
python manage.py run_processor --adapter local --mode mock --ref llm/litellm@1 --inputs-json '{"schema":"v1","params":{...}}'

# Local real (Docker)
python manage.py run_processor --adapter local --mode real --ref llm/litellm@1 --inputs-json '{...}'

# Modal (mock for smoke, real for prod)
python manage.py run_processor --adapter modal --mode mock --ref llm/litellm@1 --inputs-json '{...}'
```

## Error handling (common codes)

- `ERR_MISSING_SECRET`, `ERR_OUTPUT_DUPLICATE`, `ERR_IMAGE_PULL`, `ERR_TIMEOUT`, `ERR_FUNCTION_NOT_FOUND`

## Best practices

- Start with `mode=mock` for unit/acceptance
- Use `mode=real` for integration with containers
- Deploy by digest only; verify digest on staging/main
