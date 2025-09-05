# Contributing

This project is **docs-first**. Every change must update docs and link a GitHub Issue. Architectural changes also link an ADR.

## Workflow (Conversation → Issue → (ADR) → PR → Merge)
1. **Open an Issue** describing the smallest correct change.
2. If **architectural**, create/update an **ADR** (see `docs/source/adr/`).
3. Implement the change and **update docs** (guides, concepts, API).
4. Open a PR that **links the Issue/ADR** and lists doc files touched.
5. CI must pass:
   - Sphinx build: `-n -W` (warnings fail build)
   - Linkcheck
   - Generated docs up-to-date

## Local Dev
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r docs/requirements.txt
cd code && python manage.py docs_export --out ../docs/_generated --erd --api --schemas
sphinx-build -n -W -b html docs/source docs/_build/html
sphinx-build -b linkcheck docs/source docs/_build/linkcheck
```

## PR Checklist
- Linked Issue and (if applicable) ADR
- Docs updated (guides/concepts/API)
- Smoke commands included
- Backout steps described

## Why docs-first?
Docs are contracts. They prevent drift, speed reviews, and make changes safe.