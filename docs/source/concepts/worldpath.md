# WorldPath & Canonicalization

WorldPaths provide a unified addressing scheme for all resources in the Theory orchestrator with strict canonicalization rules.

## Simplified Path Grammar

WorldPaths use a simplified hierarchical structure with facet-based organization:

```
/artifacts/{subpath...}
/streams/{subpath...}
```

### Supported Facets

**Artifacts** (`/artifacts/`):
- Immutable files and JSON data
- Content-addressed with CID references
- Examples: `/artifacts/outputs/text/response.txt`, `/artifacts/inputs/data.json`

**Streams** (`/streams/`):
- Real-time data series (audio, video, telemetry)
- Time-ordered chunks with sequence numbers
- Examples: `/streams/audio/microphone/`, `/streams/video/camera1/`

## Canonicalization Rules

All WorldPaths undergo strict canonicalization using `canonicalize_worldpath()` from `apps.core.utils.worldpath`:

### 1. Leading Slash Required
- All paths must start with `/`
- Relative paths are not allowed

### 2. Unicode NFC Normalization
- Apply NFC (Canonical Decomposition + Canonical Composition)
- Ensures consistent representation of Unicode characters

### 3. Percent Decoding (Once Only)
- Decode percent-encoded characters **exactly once**
- Prevent double-encoding issues
- Invalid UTF-8 sequences are rejected with `ERR_PERCENT_DECODE`

### 4. Forbidden Decoded Characters
- **Forbid decoded `/` (from `%2F`)**
- Prevents path traversal attacks
- Returns `ERR_DECODED_SLASH` error
- Example: `/artifacts/outputs%2Fhidden/file.txt` → **REJECTED**

### 5. Path Cleaning
- **Collapse multiple slashes**: `//` → `/`
- **Forbid relative components**: `.` and `..` segments are rejected with `ERR_DOT_SEGMENTS`

### 6. Facet Root Validation
- Only `/artifacts/` and `/streams/` facet roots are allowed
- Invalid roots return `ERR_BAD_FACET`

### Implementation Reference

```python
# From apps.core.utils.worldpath
def canonicalize_worldpath(path: str) -> Tuple[str, Optional[str]]:
    """
    Canonicalize an absolute WorldPath. Rules:
      - Leading '/' required
      - NFC normalize
      - Percent-decode once; forbid decoded '/'
      - Collapse '//' runs
      - Forbid '.' and '..' segments
      - Only /artifacts/** or /streams/**
      - Return (normalized_path, error or None)
    """
```

## Selector Types

WorldPath selectors specify resource access patterns with strict validation:

### Exact Selectors
- Target a specific resource
- **Must NOT end with `/`**
- Validated by `enforce_selector_kind(path, kind="exact")`
- Examples: `/artifacts/outputs/text/response.txt`, `/artifacts/models/weights.bin`

### Prefix Selectors
- Target all resources under a path prefix
- **Must end with `/`**
- Validated by `enforce_selector_kind(path, kind="prefix")`
- Examples: `/artifacts/outputs/text/`, `/streams/audio/`

### Validation Errors

Selector validation returns `ERR_SELECTOR_KIND_MISMATCH` for:
- `kind="prefix"` without trailing `/`
- `kind="exact"` with trailing `/`

## Relative Path Canonicalization

For paths within write prefixes, use `canonicalize_relpath()`:

```python
def canonicalize_relpath(rel: str) -> str:
    """
    Canonicalize a POSIX relative path (used for targets inside write_prefix).
    No leading '/', no '.' or '..' segments, NFC normalize, percent-decode once, collapse slashes.
    """
```

**Rules:**
- No leading `/` allowed
- Converts `\` to `/` for cross-platform compatibility
- Same Unicode and percent-decode rules as absolute paths
- Rejects `.` and `..` segments

## Write Prefix Validation

Processors specify output locations using write prefixes with strict validation:

### Rules

1. **Must be prefix selector** (end with `/`)
2. **Must be under valid facet root** (`/artifacts/` or `/streams/`)
3. **Must pass canonicalization**
4. **Must not conflict with existing resources**

### Examples

**Valid write prefixes:**
```
/artifacts/outputs/text/
/artifacts/models/v2/
/streams/audio/processed/
/artifacts/execution/E123/
```

**Invalid write prefixes:**
```
/artifacts/outputs/text      # Missing trailing slash
/invalid/path/               # Invalid facet root
/artifacts/../outputs/       # Relative components
/artifacts/outputs%2Fhidden/ # Contains decoded slash
```

## Error Codes

The canonicalization system returns specific error codes:

- **`ERR_DECODED_SLASH`**: Path contains decoded `/` character from `%2F`
- **`ERR_DOT_SEGMENTS`**: Path contains `.` or `..` segments
- **`ERR_BAD_FACET`**: Path doesn't start with `/artifacts/` or `/streams/`
- **`ERR_PERCENT_DECODE`**: Invalid percent-encoding or UTF-8 sequence
- **`ERR_SELECTOR_KIND_MISMATCH`**: Selector doesn't match required trailing slash format

## Path Examples

### Typical Artifact Paths
```
/artifacts/outputs/text/response.txt
/artifacts/outputs/images/generated.png
/artifacts/models/llm/weights.bin
/artifacts/datasets/training/data.json
/artifacts/outputs/.../E123/outputs.json
/artifacts/inputs/data.csv
```

### Stream Paths
```
/streams/audio/microphone/chunk_001.wav
/streams/video/camera1/frame_1234.jpg
/streams/telemetry/sensors/temperature.json
/streams/effectors/speaker/audio_out.wav
```

## Usage in Implementation

### CLI Commands

The `run_processor` command validates write prefixes:

```bash
python manage.py run_processor \
  --ref llm/litellm@1 \
  --write-prefix /artifacts/outputs/text/ \  # Must end with /
  --inputs-json '{"messages":[{"role":"user","content":"Hello"}]}'
```

### Adapter Interface

All adapters receive canonicalized `write_prefix` parameters:

```python
result = adapter.invoke(
    processor_ref="llm/litellm@1",
    inputs_json=inputs,
    write_prefix="/artifacts/outputs/text/",  # Pre-validated
    execution_id=execution_id,
    registry_snapshot=registry_snapshot,
    adapter_opts=adapter_opts,
    secrets_present=secrets_present,
)
```

### Relative Path Construction

Within processors, use relative paths that get joined with write prefix:

```python
# Processor writes to relative path
relative_path = "response.txt"

# Combined with write_prefix="/artifacts/outputs/text/"
# Results in: /artifacts/outputs/text/response.txt
```

## Security Considerations

### Path Traversal Prevention

The canonicalization system prevents several attack vectors:

1. **Directory traversal**: `..` segments rejected
2. **Decoded slash injection**: `%2F` → `/` detection and rejection
3. **Double encoding**: Single decode pass prevents bypass attempts
4. **Facet isolation**: Only whitelisted facet roots allowed

### Best Practices

1. **Always canonicalize** before storing or comparing paths
2. **Validate early** in request processing using the provided functions
3. **Use the single canonicalizer** to ensure consistency across the system
4. **Handle error codes** appropriately in user-facing interfaces

## Cross-References

- {doc}`../apps/storage` - Storage layer that implements WorldPath handling
- {doc}`adapters` - Adapter interface that uses WorldPath validation
- {doc}`envelopes-and-index` - Output envelope format that includes WorldPaths
- [Storage Adapter Pattern ADR](../adr/ADR-0002-storage-adapter-pattern.md) - Design decisions for path handling
