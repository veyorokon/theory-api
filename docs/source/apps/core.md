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