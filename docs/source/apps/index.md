# Applications

These pages document each Django app with a human overview, API autodoc, and generated diagrams.

```{toctree}
:maxdepth: 1

storage
core
```

## Application Overview

### Current Apps

#### [Storage](storage)
Vendor-neutral storage abstraction that seamlessly switches between MinIO (development) and S3 (production). Demonstrates the adapter pattern in action.

#### [Core](core)  
Core functionality including user management and system utilities like documentation generation.

### Planned Apps (Future)

#### World
Manages **Artifacts** (immutable outputs) and **ArtifactSeries** (streams). Addressed by `world://artifacts/*` and `world://streams/*`.

#### Planner  
Represents **Plans** and **Transitions** living inside the World. Transitions carry predicates, write sets, and a `processor_ref`.

#### Ledger
Immutable, hash-chained event log with **Executions** (attempts) and **Events**.

#### Executor
Schedules runnable Transitions (CAS), acquires leases, reserves budget, invokes adapters, settles receipts.

#### Registry
Loads versioned Tool specs, Schemas, Prompts, Policies. Snapshots can be pinned per Plan for reproducibility.

## Design Patterns

Each application follows consistent patterns:

### Adapter Pattern
Used extensively for vendor-neutral interfaces:
- Abstract interface defines contract
- Concrete adapters implement for specific vendors  
- Service layer provides unified access

### Singleton Pattern
For services that should have single instance:
- Maintains configuration consistency
- Reduces resource overhead

### Factory Pattern  
Creates appropriate adapters based on configuration:
- Environment-specific implementations
- Transparent to calling code