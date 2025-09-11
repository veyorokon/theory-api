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

- **local**: Docker container execution on local machine
- **mock**: Simulated execution for testing/CI
- **modal**: Cloud execution via Modal platform

### Local Adapter (Docker)

```python
class LocalAdapter:
    def invoke(self, processor_ref: str, context: ExpandedContext) -> ProcessorResult:
        """Execute processor in Docker container with sandboxed access."""
        processor_spec = context.registry_snapshot.get_processor(processor_ref)
        
        # Build or pull container image (with digest pinning)
        image_uri = self.resolve_image(processor_spec.image)
        
        # Execute with resource limits and mounted world state
        result = self.docker_client.containers.run(
            image=image_uri,
            command=["/work/entrypoint.sh"],
            environment=self.prepare_env(context),
            volumes={
                context.world_mount: {"bind": "/work/world", "mode": "ro"},
                context.scratch_dir: {"bind": "/work/out", "mode": "rw"}
            },
            mem_limit=f"{processor_spec.runtime.memory_gb}g",
            cpu_period=100000,
            cpu_quota=processor_spec.runtime.cpu * 100000,
            timeout=processor_spec.runtime.timeout_s
        )
        
        return self._canonicalize_outputs(context.scratch_dir, context.write_prefix, 
                                          processor_spec.to_dict(), context.execution_id)
```

### Modal Adapter (Cloud)

```python
class ModalAdapter:
    def invoke(self, processor_ref: str, context: ExpandedContext) -> ProcessorResult:
        """Invoke Modal function with containerized processor."""
        processor_spec = context.registry_snapshot.get_processor(processor_ref)
        
        # Map to Modal function with image digest pinning
        function = self.get_modal_function(processor_spec, digest_pinned=True)
        
        # Execute with cloud resources
        result = function.remote(
            inputs=context.inputs,
            world_mount=context.world_mount,
            write_prefix=context.write_prefix,
            execution_id=context.execution_id
        )
        
        return result  # Modal returns canonical format
```

### Mock Adapter (Testing)

```python
class MockAdapter:
    def invoke(self, processor_ref: str, context: ExpandedContext) -> ProcessorResult:
        """Simulate processor execution for testing."""
        # Generate mock outputs in canonical format
        return self._generate_mock_canonical_outputs(context)
```

## ExpandedContext

Every :term:`Processor` receives the same structured context:

```python
@dataclass
class ExpandedContext:
    # Identity
    plan_id: str
    transition_id: str  
    execution_id: str
    attempt_idx: int
    
    # Configuration
    registry_snapshot: RegistrySnapshot
    policy: PolicyDoc
    
    # Inputs & Constraints  
    inputs: dict
    write_set_resolved: list[Selector]
    budget_reserved: Receipt
    
    # World Access
    world_mount: str        # Read-only world root
    scratch_dir: str        # Writable temporary space
    
    # Determinism
    seed: int
    memo_key: str
    env_fingerprint: str
```

### World Mount

The `world_mount` provides read-only access to world state:

```
/tmp/world-mount-abc123/
├── artifacts/
│   ├── script.json
│   └── scenes/001/
└── streams/  
    └── camera/frames/ (latest chunks)
```

Processors read inputs but never write directly - all outputs go through the adapter API.

## Image Resolution & Digest Pinning

Adapters support multiple image resolution strategies:

### OCI Registry (Recommended)
```yaml
image:
  oci: "ghcr.io/theory/processor:v1.2.3@sha256:abc123..."
```
Uses digest pinning from GHCR or any OCI-compliant registry for reproducible builds.

### Local Build
```yaml
image:
  build:
    context: "apps/core/processors/llm_litellm"
    dockerfile: "Dockerfile"
```
Builds image from local Dockerfile with context path.

## SDK Integration

SDKs and libraries live inside containerized processors, not in the Django runtime:

- **Isolation**: Each processor carries its own dependencies
- **Reproducibility**: Container images ensure consistent environments
- **Security**: No direct Django integration with external SDKs

## Registry Snapshots

For reproducibility, each :term:`Plan` pins a specific registry snapshot:

```json
{
  "snapshot_id": "sha256:abc123...",
  "created_at": "2025-01-01T12:00:00Z", 
  "tools": {
    "text.llm@1": { /* tool spec */ },
    "media.render@1": { /* tool spec */ }
  },
  "schemas": { /* ... */ },
  "policies": { /* ... */ }
}
```

This ensures that a plan can be re-executed months later with identical behavior, even if the registry has evolved.

Hybrid inserts:

```{include} ../../_generated/registry/index.md
```
