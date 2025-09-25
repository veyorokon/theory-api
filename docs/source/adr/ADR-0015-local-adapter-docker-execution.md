---
title: ADR-0015 — Local Adapter Docker Execution
status: Superseded
date: 2025-09-09
deciders: architect, engineer
---

# ADR-0015 — Local Adapter Docker Execution

## Status

Superseded by HTTP-first processors and transport-only adapters (see Concepts → Adapters and Registry). Containers now expose FastAPI (`/healthz`, `/run`, `/run-stream`), and adapters POST payloads over HTTP. The file-based `/work/inputs.json`/`/work/out/**` contract in this ADR reflects the legacy model.

## Context

The local adapter was initially implemented to execute processors directly as Python subprocesses within the Django application context. This approach creates several issues:

- **Isolation boundary violation**: Processors run in the same environment as the Django application, sharing dependencies and state
- **Environment-dependent behavior**: Path resolution logic varies based on current working directory, violating invariant #7 (no env logic)
- **Interface inconsistency**: Local adapter uses different I/O patterns than Modal adapter, breaking cross-adapter behavioral consistency
- **Reproducibility concerns**: Host environment variations affect processor execution determinism

The architectural decision establishes that processors should be stateless, containerized programs with standardized interfaces.

## Decision

Local adapter will execute processors as Docker/Podman containers, not as direct Python subprocesses.

**Container Execution Model:**
- Read processor specifications from registry YAML files (`image.oci`, `runtime.*`)
- Create isolated workdir under `settings.BASE_DIR/tmp/plan.key/execution.id`
- Mount workdir as `/work` inside container with read-write access
- Standardized I/O: processor reads `/work/inputs.json`, writes outputs to `/work/out/**`
- Enforce resource constraints (CPU, memory, timeout) via Docker flags
- Upload container outputs to ArtifactStore after successful execution

**Interface Contract:**
- Processors are stateless programs that read JSON inputs and write file outputs
- No direct Django model access or environment-dependent behavior
- Exit code 0 indicates success; non-zero indicates failure
- All outputs written under `/work/out/` are collected and uploaded

## Consequences

**Benefits:**
- **Isolation**: Processors run in contained environments with controlled dependencies
- **Consistency**: Local and Modal adapters use equivalent execution models
- **Reproducibility**: Container images provide deterministic execution environments
- **Security**: Processors cannot access Django application state or host resources

**Costs:**
- **Docker dependency**: Local development requires Docker/Podman installation
- **Performance overhead**: Container startup and I/O adds execution latency
- **Debugging complexity**: Processor debugging requires container inspection techniques

**Mitigations:**
- Mock adapter provides Docker-free execution for CI/CD pipelines
- Prefer pre-built container images over build-time compilation
- Mounted workdir enables direct file inspection for debugging

## Alternatives

1. **Direct Python execution** (current): Fast but breaks isolation and consistency
2. **Process isolation only**: Use subprocess with restricted environment but maintain host dependency sharing
3. **Virtual environment isolation**: Create per-processor Python environments but still share host resources

Container execution provides the strongest isolation and cross-adapter consistency guarantees.
