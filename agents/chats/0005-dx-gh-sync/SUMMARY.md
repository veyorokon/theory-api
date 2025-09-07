# Summary — 0005 [dx] gh-sync

## Scope
- Formalize Git-native coordination: Twin authors meta.yaml; files-only messaging; CI guards; PR title convention.
- Add meta schema and message validators; document protocol; standardize templates.

## Key Changes
- Added/extended validators: `validate_chat_meta.py` (schema), `validate_chat_msgs.py` (message format/sequence).
- Added CI workflow `.github/workflows/agents-meta.yml` to run validators and enforce PR title pattern.
- Added Communication Protocol doc; updated Twin/Architect/Engineer prompts to enforce files-only and CLI rule (Architect TO USER only).
- Standardized templates under `theory_api/agents/templates/`.

## Decisions
- Commit only thin artifacts (meta.yaml, SUMMARY.md, DECISION.md, prompts, and message files); raw turns stay gitignored.
- Enforce naming: chats `<id>-<area>-<slug>`, branch `feat/<area>-<slug>-<id>`, PR title `<id> [<area>] <slug>`.
- Only Architect may speak via CLI and only as TO USER with the required template.

## Outcomes
- Schema-validated chat metadata and message format; CI catches drift early.
- Clear, reproducible protocol for coordination across agents.

## Acceptance & Smoke
- Meta: `python theory_api/agents/validate_chat_meta.py $(find theory_api/agents/chats -name meta.yaml)`
- Messages: `python theory_api/agents/validate_chat_msgs.py $(find theory_api/agents/chats -maxdepth 1 -type d)`
- Docs: `make -C theory_api/docs -W html`

## Risks & Mitigations
- Path drift → CI validators + PR checklist.
- Protocol drift → prompts updated; Communication Protocol doc is source of truth.

## Docs/Generated Drift
- `_generated/**`: unchanged
- Sphinx: passes with `-W`

## Links & Artifacts
- PR: <#>
- Commit: `<sha>`
- Docs: `theory_api/agents/prompts/communication-protocol.md`

## Follow-ups
- Optional: flip GH Issue sync to live (`sync_mode: issue-live`), add gh sync job.
