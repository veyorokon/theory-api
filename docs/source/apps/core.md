# Core App

Provides fundamental system functionality including user management and system utilities.

## Purpose

Base functionality required by all other applications:
- Custom user model with email-based authentication
- Management commands for system operations
- Documentation generation utilities
- Processor execution adapters and interface contracts
- Registry-based processor specifications

## Data Model & API

```{automodule} apps.core.models
:members:
:noindex:
```

```{automodule} apps.core.management.commands.docs_export
:members:
:noindex:
```

## User Model

The core app defines a custom User model with email-based authentication:

```python
from apps.core.models import User

# Email is the username field
user = User.objects.create_user(
    username='john',
    email='john@example.com',
    password='secure_password'
)

# Authentication uses email
from django.contrib.auth import authenticate
user = authenticate(email='john@example.com', password='secure_password')
```

### User Fields

- `email` - Primary authentication field (unique)
- `bio` - Optional user biography
- `date_of_birth` - Optional birth date
- `phone_number` - Optional phone number
- `is_profile_complete` - Profile completion flag
- `created_at` - Account creation timestamp
- `updated_at` - Last modification timestamp

## Management Commands

### docs_export

Exports documentation from Django models and code structure:

```bash
python manage.py docs_export --out docs/_generated --erd --api --schemas
```

**Options:**
- `--erd` - Generate Entity Relationship Diagram from models
- `--api` - Generate API documentation from interfaces
- `--schemas` - Export JSON schemas for models

**Generated Output:**
- `erd.mmd` - Mermaid ERD diagram
- `storage_api.md` - API documentation with architecture diagrams
- `schemas.json` - JSON schemas for all models

## Configuration

```python
# Custom user model
AUTH_USER_MODEL = 'core.User'

# Authentication backend for email login
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
]
```

## Leases (Façade)

The Core app exposes a minimal, flag‑gated `LeaseManager` façade for future admission checks.
It canonicalizes facet-root paths and provides overlap detection. Runtime enforcement is
disabled by default (`LEASES_ENABLED=False`).

**Features:**
- Facet-root paths only (`/plan`, `/artifacts`, `/streams`, `/scratch`)
- Canonicalization: lowercase, collapse `//`, percent-decode once, Unicode NFC; forbid `.`/`..`
- Trailing slash: exact → no slash; prefix → must end with slash
- API: `LeaseManager.acquire(plan_id, selectors, *, reason=None) -> LeaseHandle`; `LeaseHandle.release()`; context-manager sugar
- Flag: `LEASES_ENABLED`; current behavior is no-op
- Future: scheduler/admission enforces plan-scoped leases using this façade

```python
from apps.core.leases import LeaseManager, paths_overlap, canonicalize_selector

lm = LeaseManager(enabled=False)  # façade is a no‑op until enabled in future work
handle = lm.acquire("plan-123", [
    {"kind": "prefix", "path": "/artifacts/out/"},
])

# Context manager sugar
with lm("plan-456", [{"kind": "exact", "path": "/artifacts/result.json"}]) as handle:
    # lease held during block execution
    pass

# Overlap helpers (path-only; plan scoping handled by API callers)
paths_overlap("/artifacts/out", "/artifacts/out/frames")  # True
paths_overlap("/artifacts/foo", "/artifacts/foobar")      # False
```

## Processor Interface Contract

Processors are stateless, containerized programs that execute within isolated Docker containers. They provide a standardized interface for processing inputs and generating outputs.

### Interface Specification

**Input Contract:**
- Processors read JSON inputs from `/work/inputs.json` inside the container
- Input JSON contains all necessary parameters and data references
- Attachment references use `{"$artifact": "/artifacts/path"}` format

**Output Contract:**
- All outputs must be written under `/work/out/` directory
- Files can be organized in subdirectories (e.g., `/work/out/text/response.txt`)
- Exit code 0 indicates success; non-zero indicates failure
- Successful execution generates canonical outputs with index artifact at `/artifacts/execution/<id>/outputs.json`
- See {doc}`Processor Outputs </guides/processor-outputs>` for canonical format specification

**Environment Variables:**
- `THEORY_OUTPUT_DIR=/work/out` - Standard output directory
- Secret environment variables injected based on registry `secrets` specification

**Container Execution:**
- Working directory: `/work`
- Read-write mount: Host workdir mounted at `/work`
- Resource constraints: CPU, memory, timeout enforced via Docker flags
- Isolated execution: No access to Django models or host resources

### Registry Integration

Processors are defined by YAML specifications in `apps/core/registry/processors/`:

```yaml
ref: llm/litellm@1
description: LLM processor using LiteLLM for multi-provider support
version: 1
image:
  dockerfile: apps/core/processors/llm_litellm/Dockerfile
  oci: docker.io/library/python:3.11-slim
entrypoint:
  cmd: ["python", "/app/processor.py"]
runtime:
  cpu: 1
  memory_gb: 0.5
  timeout_s: 300
secrets:
  - OPENAI_API_KEY
```

### Adapter Implementation

**Local Adapter (Docker + Mock Mode):**
- Reads registry specification for processor configuration
- Creates isolated workdir under `settings.BASE_DIR/tmp/plan_id/execution_id`
- Default mode executes containers with resource constraints and uploads via `ArtifactStore`
- `mode="smoke"` fabricates outputs locally (no Docker/MinIO) for unit-style tests

**Modal Adapter:**
- Uses registry `image.oci` reference for Modal execution
- Identical I/O contract with different execution environment
