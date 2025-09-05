# Predicates

Predicates are first-class contracts that govern execution. Three scopes:

- **admission**: gates runnable (e.g., `artifact.exists`).
- **success**: gates succeeded (e.g., `json.schema_ok`). 
- **invariant**: continuous; if violated, emit `predicate.regressed`.

## Predicate Scopes

### Admission Predicates

Gate whether a :term:`Transition` can start executing:

```yaml
- scope: admission
  id: artifact.exists@1
  args:
    path: world://artifacts/script.json

- scope: admission  
  id: budget.available@1
  args:
    required_usd_micro: 50000
```

Common admission predicates:
- `artifact.exists` - Required input files present
- `budget.available` - Sufficient funds reserved
- `lease.acquirable` - Write paths available  
- `dependency.satisfied` - Upstream transitions completed

### Success Predicates

Validate that a transition achieved its intended outcome:

```yaml
- scope: success
  id: artifact.exists@1
  args:
    path: world://artifacts/final-video.mp4

- scope: success
  id: json.schema_ok@1
  args:
    path: world://artifacts/metadata.json
    schema_ref: media.metadata@1
```

Common success predicates:
- `file.size_gt` - Output file meets minimum size
- `json.schema_ok` - Structured data is valid
- `http.get.200` - Service endpoint is healthy
- `test.passes` - Unit/integration tests succeed

### Invariant Predicates

Continuously monitor system consistency:

```yaml  
- scope: invariant
  id: disk.space_available@1
  args:
    min_bytes: 1073741824  # 1GB

- scope: invariant
  id: service.healthy@1
  args:
    endpoint: "https://api.example.com/health"
```

If an invariant predicate flips from `true` to `false`, the system emits a `predicate.regressed` event. Policy determines whether to:
- Pause affected transitions
- Trigger repair workflows  
- Escalate to human operators

## Built-in Predicates

### File & Data Predicates

```yaml
# File operations
artifact.exists@1:          # File exists at path
  args: {path: str}
  
file.size_gt@1:            # File size exceeds threshold  
  args: {path: str, min_bytes: int}
  
json.schema_ok@1:          # JSON validates against schema
  args: {path: str, schema_ref: str}

# Stream predicates  
series.has_new@1:          # New chunks since watermark
  args: {path: str, min_idx: int}
```

### System Predicates

```yaml  
# Resource availability
budget.available@1:        # Budget sufficient for estimate
  args: {required_usd_micro: int}
  
disk.space_available@1:    # Disk space above threshold
  args: {min_bytes: int}

# Network & services  
http.get.200@1:           # HTTP endpoint returns success
  args: {url: str, timeout_ms: int}
  
dns.resolves@1:           # DNS name resolves
  args: {hostname: str}
```

### Test & Quality Predicates

```yaml
# Code quality
tests.pass@1:             # Test suite passes
  args: {path_or_glob: str, timeout_ms: int}
  
lint.clean@1:             # Code passes linting  
  args: {path: str, rules: list[str]}

# Media quality
image.resolution_min@1:   # Image meets resolution
  args: {path: str, min_width: int, min_height: int}
  
audio.duration_between@1: # Audio duration in range
  args: {path: str, min_ms: int, max_ms: int}
```

## Custom Predicates

Define domain-specific predicates by implementing the predicate interface:

```python
@predicate("my_domain.custom_check@1")
def custom_predicate(args: dict, world_context: dict) -> bool:
    """Custom business logic validation."""
    # Access world state via world_context
    # Return True if predicate passes
    pass
```

Predicates receive:
- `args` - Parameters from the predicate definition  
- `world_context` - Read-only access to relevant world state
- Return `bool` - Whether the predicate currently passes

This enables domain-specific rules while maintaining the same execution semantics.