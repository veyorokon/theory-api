# theory_api/agents — Local coordination

This folder contains AI coordination **chats** for small, numbered slices of work.

## Layout
```
theory_api/agents/
  chats/
    0004-rt-tests-litellm/
      meta.yaml
      001-to-engineer.md
      002-to-architect.md
      SUMMARY.md
      DECISION.md
      turns/           # raw chatter (gitignored)
```

## Conventions
- **ID:** zero-padded (`0004`), **area:** `rt|ld|st|ui|dx|ad|dc`, **slug:** short-kebab.
- **Folder:** `theory_api/agents/chats/<id>-<area>-<slug>/`
- **Branch:** `feat/<area>-<slug>-<id>` (or `fix/...`)
- **PR title:** `<id> [<area>] <slug>`

## meta.yaml (required keys)
```yaml
id: 0004
slug: tests-litellm
area: rt
title: Align tests to LiteLLM substrate
owner: architect           # or engineer|twin
state: open                # open|review|merged|closed
branch: feat/rt-tests-litellm-0004
created: 2025-09-05T00:00:00Z
notes: Tests-only; no behavior change.
```

## What to commit vs ignore
- Commit: `meta.yaml`, `SUMMARY.md`, `DECISION.md`.
- Ignore: `turns/**`, dumps, screenshots, secrets.