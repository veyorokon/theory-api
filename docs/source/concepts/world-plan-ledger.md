# World, Plan, and Ledger

The **World** is the single substrate. **Plan** is a facet (`world://plan/...`) with Transitions. **Ledger** is the immutable event stream.

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

## The World

The :term:`World` is Theory's unified state substrate. Everything exists as addressable resources:

- **Artifacts** (`world://artifacts/*`) - Immutable files and JSON data
- **Streams** (`world://streams/*`) - Real-time data flows  
- **Plan** (`world://plan/*`) - Execution graph as data

### Why Unified?

A unified substrate removes phase coupling and lets agents plan or act at any time under the same safety rules. There's no artificial distinction between "planning phase" and "execution phase" - both operate on the same World.

## Plans as Data

A :term:`Plan` is just another facet of the World. It contains:

- **Transitions** - Proposed mutations with predicates
- **Dependencies** - DAG edges between transitions
- **Budget** - Resource limits and accounting
- **Policy** - Execution rules and constraints

Plans are addressable and mutable:
```
world://plan/transitions/write-script/
world://plan/transitions/render-video/
world://plan/dependencies/script-to-video/
```

## The Ledger

The :term:`Ledger` provides an immutable, hash-chained audit trail:

```{mermaid}
sequenceDiagram
    participant T as Transition
    participant E as Executor
    participant L as Ledger
    participant W as World
    
    T->>E: becomes runnable
    E->>L: execution.started
    E->>W: mutate artifacts
    W->>L: artifact.produced
    E->>L: execution.succeeded
```

### Event Types

- `execution.started` - Executor begins work
- `artifact.produced` - New file/data created
- `predicate.checked` - Rule evaluation 
- `execution.succeeded/failed` - Completion status
- `budget.settled` - Resource accounting

### Hash Chain

Each event includes:
- `prev_hash` - Hash of previous event
- `this_hash` - BLAKE3 hash of canonical event JSON
- `seq` - Sequence number within plan

This provides tamper-evident history and enables audit trails.

## Execution Flow

1. **Admission** - Transition becomes runnable when dependencies, predicates, budget, and leases align
2. **Reserve** - Executor reserves budget and acquires path leases  
3. **Apply** - Processor receives ExpandedContext and acts on World
4. **Settle** - Actual costs recorded, leases released, events logged

The beauty: this same flow works for simple scripts, complex media pipelines, real-time agents, and organizational workflows.