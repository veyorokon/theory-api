# Glossary

```{glossary}
World
  The canonical state substrate addressed by `world://` paths. Contains artifacts, streams, and plan facets.

Plan  
  A facet of the World describing proposed Transitions to mutate it, governed by Predicates, budget, and policy.

Transition
  A single proposed mutation of the World referencing a `processor_ref`, `inputs`, `write_set`, and predicates.

Ledger
  The immutable event log (hash-chained) of everything that happened within a Plan.

Processor
  A tool or agent invoked by the executor via adapter (e.g., Modal). Receives an ExpandedContext and acts.

Predicate
  A declarative rule (admission/success/invariant) used to gate or monitor Transitions.

Facet
  A namespaced slice of the World (e.g., `world://plan/…`, `world://artifacts/…`, `world://streams/…`).

Lease
  A lock acquired on a set of world paths (exact/prefix) to ensure safe parallel writes.

ExpandedContext
  The structured input for processors: plan/transition IDs, policy, registry snapshot, world mount, deltas, etc.

Adapter
  Component that maps `processor_ref` to runnable functions (e.g., Modal functions, local tools).

StorageInterface
  Abstract base class defining the contract for storage adapters (MinIO, S3, etc.).

Receipt
  Resource consumption record with vectors for USD, CPU, GPU, IO, etc.

Budget
  Resource limits enforced via reserve→settle accounting to prevent runaway costs.
```