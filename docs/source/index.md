# Theory Orchestrator

A universal, event-driven framework to achieve complex goals under budget and policy.  
**Core ontology:** the **World** (state), **Plan** (proposed transitions), **Ledger** (history), with **Processors** (tools/agents) acting under **Predicates** (rules).

```{toctree}
:maxdepth: 2
:caption: Guides

guides/getting-started
guides/ci-cd
contributing
```

```{toctree}
:maxdepth: 2
:caption: Concepts

concepts/north-star
concepts/storage-planes
concepts/world-plan-ledger
concepts/facets-and-paths
concepts/ledger-events
concepts/predicates
concepts/providers
concepts/registry-and-adapters
concepts/agents-and-cognition
glossary
```

```{toctree}
:maxdepth: 2
:caption: Applications

apps/index
apps/storage
apps/core
```

```{toctree}
:maxdepth: 2
:caption: Use Cases

use-cases/run-processor
use-cases/media-generation
use-cases/ci-cd
use-cases/realtime-facetime
```

```{toctree}
:maxdepth: 1
:caption: Architecture Decisions

adr/index
```

```{toctree}
:maxdepth: 1
:caption: Runbooks

runbooks/deployments
```

## Overview

Theory provides a unified substrate for:
- **Media Pipelines** - Automated content generation
- **Real-time Agents** - Persistent conversations and streaming  
- **CI/CD Workflows** - Software deployment automation
- **Embodied Systems** - Robotics and simulation control

## Architecture

```{mermaid}
flowchart TD
  subgraph World
    A[world://artifacts/*]
    B[world://plan/transitions/*] 
    C[world://streams/*]
  end
  P[Planner] -->|propose| B
  E[Executor] -->|apply| A
  E -->|emit| L[(Ledger)]
  L -->|delta| E
```

## Quick Start

1. Install dependencies and run migrations
2. Start development environment: `docker-compose up`
3. Create your first plan and transitions
4. Watch the executor apply changes to the World

See [Getting Started](guides/getting-started) for detailed setup instructions.# Documentation trigger Thu Sep  4 22:52:49 EDT 2025
