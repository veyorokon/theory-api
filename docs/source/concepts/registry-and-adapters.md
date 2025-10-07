# Registry & Adapters

- Registry: per-processor YAML specs colocated with the processor
- Adapters: transport-only bridges to HTTP processors (local Docker or Modal)

## Registry System

The registry provides versioned, immutable specifications for all system components:

### Processor Specifications

`code/apps/core/processors/<ns>_<name>/registry.yaml`:

```yaml
ref: llm/litellm@1

image:
  platforms:
    amd64: ghcr.io/owner/repo/llm-litellm@sha256:<amd64>
    arm64: ghcr.io/owner/repo/llm-litellm@sha256:<arm64>
  default_platform: amd64

runtime:
  cpu: 1
  memory_gb: 2
  timeout_s: 600
  gpu: null

secrets:
  required: [OPENAI_API_KEY]

inputs:
  $schema: "https://json-schema.org/draft-07/schema#"
  title: "llm/litellm inputs v1"
  type: object
  additionalProperties: false
  required: [schema, params]
  properties:
    schema: { const: "v1" }
    params:
      type: object
      additionalProperties: false
      required: [messages, model]
      properties:
        model: { type: string }
        messages:
          type: array
          minItems: 1
          items:
            type: object
            required: [role, content]
            properties:
              role: { enum: [user, system, assistant] }
              content: { type: string }

outputs:
  # Paths are relative to the outputs/ directory
  - { path: text/response.txt, mime: text/plain }
  - { path: metadata.json, mime: application/json }
```

### Schema Definitions

```yaml
# registry/schemas/media.metadata.yaml
id: "media.metadata@1"
schema:
  type: "object"
  properties:
    title: {type: "string"}
    duration_ms: {type: "integer", minimum: 0}
    resolution:
      type: "object"
      properties:
        width: {type: "integer", minimum: 1}
        height: {type: "integer", minimum: 1}
  required: ["title", "duration_ms"]
```

### Policies

```yaml
# registry/policies/default.yaml
id: "default@1"
budget:
  max_usd_micro: 1000000  # $1 max per plan
retry:
  max_attempts: 3
  backoff_ms: [1000, 5000, 15000]
leases:
  default_ttl_s: 3600
  enable_path_leases: true
```

## Adapter System

- local: Docker container → WebSocket (`/healthz`, `/run` with `theory.run.v1` subprotocol)
- modal: Web endpoint → WebSocket (same payload/envelope; deployed by digest)

## Uniform Adapter API

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

### Parameters

- **processor_ref**: Registry reference (e.g., `llm/litellm@1`)
- **inputs_json**: Processor input data (including `mode`)
- **write_prefix**: WorldPath prefix for outputs (must end with `/`)
- **execution_id**: Unique execution identifier
- **registry_snapshot**: Complete registry state at execution time
- **adapter_opts**: Adapter-specific configuration options
- **secrets_present**: List of available secret names (names only, never values)

### Return Value

All adapters return consistent **envelope** format.

## Implementation Details

### Local Adapter Details

- **Object wrapper**: writes `{"outputs": [...]}` index
- **Mock vs real**: `mode="mock"` synthesizes outputs; `mode="real"` launches Docker and uploads via ArtifactStore
- **Parity with Modal**: Same success/error envelopes

### Modal Adapter

- Deploy by digest only; drift check on invoke
- Secrets pulled from Modal secret store (names only in payloads/logs)

### Secrets Handling

Secrets are resolved outside the adapter; adapters receive `secrets_present` (names only). Environment fingerprints list names, never values.

## Adapter Selection

Use `localctl` or `modalctl` commands. Containers must be started before invoking:

```bash
# Local mock run - start container, run, stop
OPENAI_API_KEY=$OPENAI_API_KEY python manage.py localctl start --ref llm/litellm@1
python manage.py localctl run --ref llm/litellm@1 --mode mock --inputs-json '{...}'
python manage.py localctl stop --ref llm/litellm@1

# Local real run - same workflow with mode=real
OPENAI_API_KEY=$OPENAI_API_KEY python manage.py localctl start --ref llm/litellm@1
python manage.py localctl run --ref llm/litellm@1 --mode real --inputs-json '{...}'
python manage.py localctl stop --ref llm/litellm@1

# Modal run - deploy, sync secrets, run, stop
GIT_BRANCH=feat/test GIT_USER=veyorokon \
  python manage.py modalctl start --ref llm/litellm@1 --env dev --oci ghcr.io/...@sha256:...
python manage.py modalctl sync-secrets --ref llm/litellm@1 --env dev
python manage.py modalctl run --ref llm/litellm@1 --mode mock --inputs-json '{...}'
python manage.py modalctl stop --ref llm/litellm@1 --env dev
```

## Best Practices

- Mock runs (`mode=mock`) for fast tests and smoke checks
- Real runs (`mode=real`) for Docker-based integration
- Promote the same pinned digest to Modal for prod
- Never log secret values; rely on `secrets_present`
