# Registry & Adapters

- **Registry**: versioned specs for tools, schemas, prompts, and policies.
- **Adapters**: map `processor_ref` → runnable function (e.g., Modal). The executor only speaks a thin adapter API.
- **ExpandedContext** is passed to processors (never raw DB access).

## Registry System

The registry provides versioned, immutable specifications for all system components:

### Tool Specifications

```yaml
# registry/tools/text.llm.yaml
id: "text.llm@1"
name: "Large Language Model Text Generation"
adapter: "modal"
entry_point: "modal_functions.llm_generate"
inputs:
  - name: "prompt"  
    type: "string"
    required: true
  - name: "model"
    type: "string" 
    default: "gpt-4"
outputs:
  - name: "text"
    type: "string"
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

Adapters translate abstract `processor_ref` identifiers into concrete execution:

### Modal Adapter

```python
class ModalAdapter:
    def invoke(self, processor_ref: str, context: ExpandedContext) -> ProcessorResult:
        """Invoke a Modal function with the given context."""
        tool_spec = context.registry_snapshot.get_tool(processor_ref)
        
        # Map to Modal function
        function = self.get_modal_function(tool_spec.entry_point)
        
        # Execute with timeout and resource limits
        result = function.remote(
            inputs=context.inputs,
            world_mount=context.world_mount,
            write_paths=context.write_set_resolved
        )
        
        return ProcessorResult(
            success=True,
            outputs=result.outputs,
            receipt=result.usage,
            artifacts=result.produced_artifacts
        )
```

### Local Adapter  

```python
class LocalAdapter:
    def invoke(self, processor_ref: str, context: ExpandedContext) -> ProcessorResult:
        """Run a local tool/script with sandboxed filesystem access."""
        tool_spec = context.registry_snapshot.get_tool(processor_ref)
        
        # Execute in subprocess with restricted permissions
        result = subprocess.run(
            [tool_spec.entry_point] + context.inputs,
            cwd=context.scratch_dir,
            timeout=tool_spec.timeout_s,
            capture_output=True
        )
        
        return self.parse_result(result)
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