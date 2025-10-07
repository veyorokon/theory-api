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

Containers must be started before invoking:
- **Local**: Use `localctl start` (injects secrets, starts container from pinned digest or newest build)
- **Modal**: Use `modalctl start` (deploys by digest) + `modalctl sync-secrets` (syncs secrets separately)

| Adapter | Container Start | Digest Source |
|---------|----------------|---------------|
| local   | `localctl start` | Pinned registry digest or newest build tag |
| modal   | `modalctl start --oci <digest>` | Explicit digest (amd64 from registry) |

Notes:
- "Pinned digest" comes from `code/apps/core/processors/<ns>_<name>/registry.yaml` (`image.platforms.{amd64,arm64}`).
- Modal deployments require explicit digest; drift check validates deployed digest matches registry.
- No auto-starting or auto-building; each command does exactly one thing.

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
python manage.py localctl run --ref llm/litellm@1 --platform amd64 --mode mock --json
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
# Local WebSocket - start, run, stop
OPENAI_API_KEY=$OPENAI_API_KEY python manage.py localctl start --ref llm/litellm@1
python manage.py localctl run --ref llm/litellm@1 --mode mock --inputs-json '{"schema":"v1","params":{...}}'
python manage.py localctl stop --ref llm/litellm@1

# Modal WebSocket - start, sync secrets, run, stop
GIT_BRANCH=feat/test GIT_USER=veyorokon \
  python manage.py modalctl start --ref llm/litellm@1 --env dev --oci ghcr.io/...@sha256:...
python manage.py modalctl sync-secrets --ref llm/litellm@1 --env dev
python manage.py modalctl run --ref llm/litellm@1 --mode mock --inputs-json '{...}'
python manage.py modalctl stop --ref llm/litellm@1 --env dev
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
