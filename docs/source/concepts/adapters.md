# Adapters (Transport Layer)

Adapters move payloads to processors over WebSocket or HTTP and validate envelopes. They do no business logic.

## Types

### LocalWsAdapter (Docker → WebSocket)

- Start container by pinned digest (select platform by host arch)
- Poll `GET /healthz`, then WebSocket `/run` with `theory.run.v1` subprotocol
- Connection lifecycle: RunOpen → events → RunResult
- Validate envelope; enforce index discipline; optional digest drift check

### ModalWsAdapter (Web endpoint → WebSocket)

- Call deployed Modal endpoint bound to the pinned digest
- WebSocket connection to Modal deployment with `theory.run.v1` subprotocol
- Same payload and envelope; enforce digest drift vs deployment

### Legacy HTTP Adapters (Deprecation Path)

- **LocalAdapter**: `POST /run` synchronous execution
- **ModalAdapter**: HTTP endpoint calls
- Support maintained during transition period

## Minimal API (Protocol)

### WebSocket Adapters (Standard)

```python
def invoke(
    *,
    ref: str,
    payload: dict,
    timeout_s: int,
    oci: dict,
    stream: bool = False,
) -> dict | Iterator[dict]
```

**Connection Flow:**
1. Health check: `GET /healthz`
2. WebSocket connection: `/run` with `theory.run.v1` subprotocol
3. Send `RunOpen` frame with payload
4. Receive events (Token|Frame|Log|Event) if streaming
5. Receive final `RunResult` frame with envelope

### Legacy HTTP API

Similar signature but uses `POST /run` for synchronous execution.

**Key Points:**
- `payload.mode ∈ {mock, real}`; adapters never infer from env
- In PR lane, use `mode=mock` (hermetic; no secrets)
- Envelopes identical across adapters; only transport differs
- WebSocket provides real-time streaming; HTTP is synchronous

## Image Selection Behavior

The adapter chooses which image to run or call based on adapter type and the `--build` flag passed to `run_processor`:

| Adapter | `--build` | Behavior |
|---------|-----------|----------|
| local   | true      | Uses the newest locally built, timestamped tag (build-from-source loop) |
| local   | false     | Uses the pinned registry digest from the processor's `registry.yaml` |
| modal   | any       | Ignores `--build`; performs SDK lookup of the deployed app/function bound to the pinned digest |

Notes:
- "Pinned digest" comes from `code/apps/core/processors/<ns>_<name>/registry.yaml` (`image.platforms.{amd64,arm64}`).
- Modal deployments must be created by digest; the adapter then looks up the deployed app and can perform a digest drift check.

### Platform Detection & Override

The orchestrator selects the correct platform digest based on adapter type and optional override:

| Adapter | Default Platform | Override Behavior |
|---------|-----------------|-------------------|
| local   | Host platform (arm64 on Mac M1/M2, amd64 on x86_64) | `--platform` overrides host detection |
| modal   | `amd64` (Modal runs x86_64 only) | `--platform` can override if needed |

**Why this matters**:
- Mac M1/M2 developers run arm64 locally but Modal requires amd64
- Registry contains separate digests for each platform
- Digest drift detection fails if platform mismatch occurs

**Platform override example**:
```bash
# Force amd64 digest on arm64 Mac (for testing Modal-like behavior locally)
python manage.py run_processor --ref llm/litellm@1 --adapter local --platform amd64 --json
```

**Implementation** (`orchestrator_ws.py:81`):
```python
def invoke(
    *,
    ref: str,
    platform: str | None = None,  # Override platform for digest selection
    ...
) -> Dict[str, Any] | Iterator[Dict[str, Any]]:
```

## Selection examples

```bash
# Local WebSocket mock (no external deps)
python manage.py run_processor --adapter local --mode mock --ref llm/litellm@1 --inputs-json '{"schema":"v1","params":{...}}'

# Local WebSocket real (Docker)
python manage.py run_processor --adapter local --mode real --ref llm/litellm@1 --inputs-json '{...}'

# Modal WebSocket (mock for smoke, real for prod)
python manage.py run_processor --adapter modal --mode mock --ref llm/litellm@1 --inputs-json '{...}'
```

## Error handling (common codes)

### WebSocket Specific
- `ERR_WS_TIMEOUT` - WebSocket connection timeout
- `ERR_WS_PROTOCOL` - WebSocket protocol violation
- `ERR_WS_CLOSE` - Unexpected connection close

### General
- `ERR_MISSING_SECRET`, `ERR_OUTPUT_DUPLICATE`, `ERR_IMAGE_PULL`, `ERR_TIMEOUT`, `ERR_FUNCTION_NOT_FOUND`

## Best practices

- Start with `mode=mock` for unit/acceptance
- Use `mode=real` for integration with containers
- Deploy by digest only; verify digest on staging/main
