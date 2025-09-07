# Core App

Provides fundamental system functionality including user management and system utilities.

## Purpose  

Base functionality required by all other applications:
- Custom user model with email-based authentication
- Management commands for system operations
- Documentation generation utilities

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
