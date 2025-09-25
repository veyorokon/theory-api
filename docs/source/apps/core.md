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

## Processor Interface Contract (HTTP-first)

Processors are stateless containers exposing a FastAPI service with one contract. Adapters are transport-only.

### HTTP Endpoints

- `GET /healthz` → `{ "ok": true }`
- `POST /run` → synchronous execution, returns canonical envelope JSON
- `POST /run-stream` (optional) → SSE stream of events; the final event carries the envelope (event name may be `done` or `settle` depending on processor)

### Payload (control plane → processor)

```json
{
  "schema": "v1",
  "execution_id": "<uuid>",
  "ref": "ns/name@ver",
  "mode": "mock" | "real",
  "inputs": { /* validated by registry inputs schema */ },
  "write_prefix": "/artifacts/outputs/.../{execution_id}/",
  "meta": { "trace_id": "<uuid>" }
}
```

Rules:
- `write_prefix` must include `{execution_id}` and end with `/`
- PR lane uses `mode="mock"` (no secrets, no egress)

### Outputs & Receipts (inside container)

- Write files under `<write_prefix>/outputs/**`
- Write `<write_prefix>/outputs.json` (sorted, wrapper `{ "outputs": [...] }`)
- Dual receipts:
  - `<write_prefix>/receipt.json`
  - `/artifacts/execution/<execution_id>/determinism.json`

See {doc}`Processor Outputs </guides/processor-outputs>` and {doc}`Envelopes & Index </concepts/envelopes-and-index>`.

### Registry Integration

Each processor directory contains a `registry.yaml` at `code/apps/core/processors/<ns>_<name>/registry.yaml` with this shape:

```yaml
ref: llm/litellm@1

image:
  platforms:
    amd64: ghcr.io/owner/repo/llm-litellm@sha256:<amd64>
    arm64: ghcr.io/owner/repo/llm-litellm@sha256:<arm64>
  default_platform: amd64

runtime:
  cpu: "1"
  memory_gb: 2
  timeout_s: 600
  gpu: null

secrets:
  required: [OPENAI_API_KEY]

inputs:
  $schema: "https://json-schema.org/draft-07/schema#"
  title: "llm/litellm inputs v1"
  type: object
  additionalProperties: false
  required: [schema, params]
  properties:
    schema: { const: "v1" }
    params:
      type: object
      additionalProperties: false
      required: [messages, model]
      properties:
        model: { type: string }
        messages:
          type: array
          minItems: 1
          items:
            type: object
            required: [role, content]
            properties:
              role: { enum: [user, system, assistant] }
              content: { type: string }

outputs:
  # Paths are relative to the outputs/ directory
  - { path: text/response.txt, mime: text/plain }
  - { path: metadata.json, mime: application/json }
```

### Adapter Implementation (transport-only)

**Local Adapter (Docker → HTTP):**
- Start container by digest (host arch → platform)
- Poll `/healthz`, then `POST /run` (or `/run-stream` for SSE)
- Validate envelope; enforce index discipline; optional digest drift check

**Modal Adapter (Web endpoint → HTTP):**
- Call deployed web endpoint bound to the pinned digest
- Same payload and envelope as local; drift check vs deployed digest
