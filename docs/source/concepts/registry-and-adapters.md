# Registry & Adapters

- **Registry**: versioned specs for tools, schemas, prompts, and policies.
- **Adapters**: map `processor_ref` → runnable function (e.g., Modal). The executor only speaks a thin adapter API.
- **ExpandedContext** is passed to processors (never raw DB access).

## Registry System

The registry provides versioned, immutable specifications for all system components:

### Processor Specifications

```yaml
# registry/processors/llm/litellm.yaml
ref: llm/litellm@1
name: "LLM processor using LiteLLM"
image:
  oci: "ghcr.io/theory/litellm:v1.2.3@sha256:abc123..."
  build:
    context: "apps/core/processors/llm_litellm"
    dockerfile: "Dockerfile"
runtime:
  cpu: 1
  memory_gb: 2
  timeout_s: 300
  gpu: false
secrets:
  required:
    - OPENAI_API_KEY
  optional:
    - ANTHROPIC_API_KEY
outputs:
  writes:
    - prefix: "/artifacts/outputs/text/"
    - prefix: "/artifacts/outputs/meta.json"
predicates:
  admission:
    - id: "budget.available@1"
      args: {required_usd_micro: 1000}
  success:
    - id: "artifact.exists@1"
      args: {path: "${outputs.text_path}"}
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

Adapters provide runtime placement for processors, mapping `processor_ref` to concrete execution environments:

- **local**: Docker-backed execution on the same host (inputs carry `mode: "mock"` for hermetic runs).
- **modal**: Cloud execution via the Modal platform.

> “mock adapter” no longer exists; instead processors honour `mode` in the inputs JSON. CI smoke tests and local quick checks simply call `run_processor … --mode mock`, regardless of adapter.

### Local Adapter (Docker + Mock mode)

Executes processors on the host. In **real mode** it uses Docker containers and ArtifactStore; in **mock mode** it fabricates deterministic outputs under the write-prefix without touching external services.

**Use cases:**
- Fast mock runs (unit-style)
- Full Docker execution for integration
- CI smoke tests (mock mode)

**Characteristics:**
- Synchronous execution
- Docker isolation in `mode="real"`
- Hermetic, no-external-deps path in `mode="mock"`

### Modal Adapter

Executes processors on Modal's serverless platform using the pinned image digest.

**Use cases:**
- Production workloads
- GPU or high-memory processors
- Warm pools for low latency

**Characteristics:**
- Pre-deployed functions (`modal deploy -m modal_app`)
- Secrets mounted by name
- Identical envelope format to local adapter

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

- Uses `image.oci` digests from the registry
- Secrets pulled from Modal secret store
- Deployed via `modal deploy -m modal_app.py`

### Secrets Handling

Secrets are resolved outside the adapter; adapters receive `secrets_present` (names only). Environment fingerprints list names, never values.

## Adapter Selection

Use the CLI `--adapter` flag and provide `--mode mock|real` as needed:

```bash
# Local mock run (no external dependencies)
python manage.py run_processor --adapter local --mode mock --ref llm/litellm@1 ...

# Local real run (Docker container)
python manage.py run_processor --adapter local --mode real --ref llm/litellm@1 ...

# Modal run (always real mode)
python manage.py run_processor --adapter modal --mode real --ref llm/litellm@1 ...
```

## Best Practices

- Mock runs (`mode=mock`) for fast tests and smoke checks
- Real runs (`mode=real`) for Docker-based integration
- Promote the same pinned digest to Modal for prod
- Never log secret values; rely on `secrets_present`
