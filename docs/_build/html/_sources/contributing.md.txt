# Contributing to Docs

We follow **Docs-as-Contracts**:
- Reference content is generated from source of truth (registry, schemas, models).
- Human-written pages live in `docs/source/**`.
- Generated pages live in `docs/_generated/**`. Do not edit by hand.

## Workflow

1. Write/edit Markdown (MyST) under `docs/source/**`.
2. Run exporters to populate `_generated/**`:
   ```bash
   python manage.py docs_export --out docs/_generated --erd --api --schemas
   ```
3. Build docs:
   ```bash
   make -C docs html
   ```
4. Commit both `source/**` and `_generated/**`.

## Style

- Use clear, active voice.
- Prefer examples and diagrams.
- Link glossary terms with `:term:`World`` etc.
- Follow MyST Markdown syntax for cross-references.

## Page Types

### Manual Pages
Pure human writing for concepts, guides, and architectural decisions.

### Hybrid Pages  
Combine human context with generated content using `{include}` directives:

```markdown
## Data Model

{automodule} apps.storage.models
:members:

## Architecture (Generated)

{include} ../../_generated/diagrams/storage-architecture.md
```

### Generated Pages
Pure machine output in `_generated/` - never edit by hand.