# Architecture Decision Records

```{toctree}
:maxdepth: 1

ADR-template
ADR-0001-docs-as-contracts
ADR-0002-storage-adapter-pattern
ADR-0003-branch-strategy-cicd
ADR-0015-local-adapter-docker-execution
```

## Overview

Architecture Decision Records (ADRs) document important architectural decisions along with their context and consequences. Each ADR captures:

- **Status** - Proposed, Accepted, Deprecated, or Superseded
- **Context** - The situation that required a decision
- **Decision** - What was decided and why
- **Consequences** - Positive and negative outcomes
- **Alternatives** - Other options considered

## Active ADRs

### [ADR-0001: Docs as Contracts](ADR-0001-docs-as-contracts)
Establishes that reference documentation must be generated from source of truth to prevent drift.

### [ADR-0002: Storage Adapter Pattern](ADR-0002-storage-adapter-pattern) 
Defines the vendor-neutral storage abstraction using the adapter pattern.

### [ADR-0003: Branch Strategy and CI/CD Pipeline](ADR-0003-branch-strategy-cicd)
Establishes branching workflow and automated deployment pipeline for safe production releases.

### [ADR-0015: Local Adapter Docker Execution](ADR-0015-local-adapter-docker-execution)
Defines container-based execution model for local adapter to ensure isolation and consistency.

## Writing ADRs

Use the [ADR Template](ADR-template) when documenting new architectural decisions. Focus on:

1. **Clear context** - Why was this decision needed?
2. **Explicit tradeoffs** - What alternatives were considered?
3. **Concrete consequences** - What are the positive and negative outcomes?
4. **Future implications** - How might this decision affect future work?

## ADR Lifecycle

```{mermaid}
stateDiagram-v2
    [*] --> Proposed
    Proposed --> Accepted: team_approval
    Proposed --> Rejected: team_rejection
    Accepted --> Deprecated: better_solution
    Accepted --> Superseded: replacement_adr
    Deprecated --> [*]
    Superseded --> [*]
    Rejected --> [*]
```

## Guidelines

- **One decision per ADR** - Keep scope focused
- **Immutable once accepted** - Don't edit, create new ADR to supersede
- **Link related ADRs** - Show relationships between decisions  
- **Include concrete examples** - Help readers understand implications
- **Update status** - Mark deprecated/superseded ADRs clearly