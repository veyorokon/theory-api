# North Star (Non-normative)

This page summarizes the guiding principles that shape Theory's architecture. It is guidance only; for binding decisions see [ADRs](../adr/index.md) and app documentation.

## Core Principles

- **Plan ≡ World (facet)**: Plans live as data within the World under canonical paths, not as separate abstractions
- **Events as truth**: Hash-chained ledger provides tamper-evident history with cryptographic integrity  
- **Admission before spend**: Reserve budgets on start, settle on finish - mathematical guarantees prevent drift
- **Processors via adapters**: Modal-first execution with uniform interface regardless of compute substrate
- **Predicates are first-class**: Declarative gates that control admission, verify success, and detect invariant violations

## Why It Matters

- **Unified model**: No artificial boundaries between planning, execution, and state management
- **Audit by design**: Every mutation recorded with hash chains, enabling perfect replay and forensics
- **Budget safety**: Integer-only accounting with reserve/settle prevents cost overruns across retries
- **Reproducibility**: Pinned registry snapshots capture exact tool versions for deterministic replay
- **Self-healing**: Invariant predicates detect regressions and trigger repair transitions automatically
- **Scale flexibility**: From batch pipelines to real-time streaming with the same primitive operations
- **Vendor independence**: Adapter pattern enables transparent switching between compute/storage providers

## Architecture Goals

Theory orchestrates complex, stateful goals through composable primitives:

- Media generation pipelines with progress tracking
- Real-time conversational agents with streaming I/O
- CI/CD workflows with dependency management
- Embodied simulation control (robotics/Unity)  
- Dynamic tool generation and meta-programming

## Related Documentation

- [ADR-0001: Docs as Contracts](../adr/ADR-0001-docs-as-contracts.md) - Documentation philosophy
- [ADR-0002: Storage Adapter Pattern](../adr/ADR-0002-storage-adapter-pattern.md) - Vendor-neutral storage
- [ADR-0003: Branch Strategy and CI/CD](../adr/ADR-0003-branch-strategy-cicd.md) - Development workflow
- [World/Plan/Ledger Concepts](world-plan-ledger.md) - Core execution model
- [Facets and WorldPaths](facets-and-paths.md) - Path grammar and addressing
- [Predicates](predicates.md) - Declarative control flow

## Future Enhancements

Areas from the root narratives that may warrant future documentation:
- Execution loop detailed mechanics (CAS admission, lease management)
- Registry snapshot implementation details
- Event hash-chaining cryptographic specifics
- StreamBus real-time architecture patterns