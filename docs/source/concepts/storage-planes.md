# Storage Planes (Non-normative)

Theory standardizes on four distinct storage planes and a single path grammar. This is guidance for understanding the architecture; for implementation details see [Storage app documentation](../apps/storage.md) and [ADR-0002](../adr/ADR-0002-storage-adapter-pattern.md).

## The Four Planes

### Truth (PostgreSQL)
- **Purpose**: Source of truth for all structured, transactional data
- **Contains**: Plans, Transitions, Events, Executions, Leases, Budgets, Policies
- **Guarantees**: ACID transactions, referential integrity, unique constraints
- **Access**: Django ORM for models, direct SQL for performance-critical paths

### Artifacts (S3/MinIO)
- **Purpose**: Immutable files and structured JSON artifacts
- **Contains**: World state under `/world/{tenant}/{plan}/artifacts/*` paths
- **Guarantees**: Content addressing via checksums, presigned URLs for direct access
- **Access**: StorageService adapter pattern enables transparent S3/MinIO switching

### Streams (Redis)
- **Purpose**: Low-latency, ephemeral chunk series for real-time data
- **Contains**: Streaming data under `/world/{tenant}/{plan}/streams/*` paths
- **Guarantees**: Ordering preservation, backpressure control, configurable retention
- **Access**: StreamBus interface with append/read/seal operations

### Scratch (Modal Volumes)
- **Purpose**: Ephemeral processor workdirs and computation caches
- **Contains**: Temporary files, intermediate results, build artifacts
- **Guarantees**: None - never a source of truth, cleared after execution
- **Access**: Local filesystem within processor execution context only

## WorldPath Grammar

All planes share a canonical path format for uniform addressing:

```
/world/{tenant}/{plan}/{facet}/{subpath...}
```

**Rules**:
- Lowercase only, no dots or double-slashes
- Single leading slash, no trailing slash (unless directory convention)
- Tenant and plan are required identifiers
- Facet labels are free-form: "artifacts", "streams", "plan", "senses", "effectors"

**Examples**:
```
/world/acme/plan-123/artifacts/scenes/001/script.json
/world/acme/plan-123/streams/senses/mic/audio
/world/acme/plan-123/plan/transitions/t-001.json
```

## Adapter Pattern Benefits

The storage adapter abstraction provides:

- **Environment transparency**: Same code works across dev/staging/production
- **Vendor flexibility**: Switch storage providers via configuration without code changes
- **Testing isolation**: Use local adapter smoke mode or in-memory implementations for tests
- **Consistent API**: Uniform interfaces hide backend implementation complexity

## Storage Selection Guidelines

Choose the appropriate plane based on data characteristics:

| Characteristic | Truth | Artifacts | Streams | Scratch |
|---------------|-------|-----------|---------|---------|
| Durability | Forever | Forever | Configurable | None |
| Consistency | Strong | Eventual | Ordered | None |
| Latency | ~10ms | ~100ms | ~1ms | Local |
| Size Limits | MB | GB+ | KB chunks | GB |
| Query Support | Full SQL | Prefix list | Sequential | None |

## Related Documentation

- [ADR-0002: Storage Adapter Pattern](../adr/ADR-0002-storage-adapter-pattern.md) - Design decisions
- [Storage App](../apps/storage.md) - Implementation APIs and usage
- [Facets and WorldPaths](facets-and-paths.md) - Complete path grammar specification
- [World/Plan/Ledger](world-plan-ledger.md) - How storage planes support execution

## Future Enhancements

Areas from the root narratives that may warrant future documentation:
- StreamBus Redis implementation specifics
- Artifact content-addressing and CID generation
- Lease management for parallel write coordination
- Cross-plane consistency patterns and best practices
