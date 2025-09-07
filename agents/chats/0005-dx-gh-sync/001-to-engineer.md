-- TO ENGINEER:

STATUS
We’re formalizing Git‑native coordination. The Digital Twin (preference model) now authors each chat’s meta.yaml. We need CI guardrails and prompt updates so all agents initialize with the same rules.

PLAN (smallest correct set)
1) Validator (schema)
   - Update `theory_api/agents/validate_chat_meta.py` schema to include: `scope`, `non_goals`, `acceptance`, `outputs`, `gh`, `ci_gates`.
2) GitHub Action (validation + dry‑run sync)
   - Add `.github/workflows/agents-meta.yml`:
     - Validate meta files with the schema.
     - Enforce PR title pattern: `0005 [dx] gh-sync`.
     - Print dry‑run summary of chats with `gh.sync_mode=issue-dryrun`.
3) Prompts (clarify init & ownership)
   - `theory_api/agents/prompts/digital-twin.md`: Twin is preference model; Twin authors meta.yaml; chats/ paths; branch/PR conventions.
   - `theory_api/agents/prompts/AGENTS.md`: thin artifacts; chats tree; conventions; explicit “Twin authors meta.yaml”.
   - `theory_api/agents/prompts/architect.md`: “Start from the Twin’s meta.yaml; produce 001-to-engineer.md; use branch from meta.”
   - `theory_api/agents/prompts/engineer.md`: “Read meta.yaml + 001; create branch if missing; land smallest reversible diff; run acceptance.”
4) (Optional later) issue‑live toggle
   - Keep sync in dry‑run for this chat; we’ll flip to live later.

5) Templates location + names (canonicalize)
   - Move existing templates into `theory_api/agents/templates/` and standardize names:
     - `theory_api/agents/templates/meta.template.yaml`
     - `theory_api/agents/templates/decision.template.md`
     - `theory_api/agents/templates/summary.template.md`
   - Update any references (if present) to point to this new path and names.

6) Communication Protocol (files-only + CLI rule)
   - Add `theory_api/agents/prompts/communication-protocol.md` with rules:
     - All inter‑agent comms are file‑only under `theory_api/agents/chats/<id>-<area>-<slug>/`.
     - Message filenames: `<seq>-to-<role>.md`, zero‑padded `seq`.
     - YAML front matter required (from/to/chat/seq/ts/purpose), then a `-- TO <ROLE>:` header.
     - Only the Architect may use CLI, and only for a TO USER message with the required template; Twin/Engineer must not print to CLI.
   - Update prompts:
     - `prompts/digital-twin.md`: add “files‑only” rule; forbid CLI for Twin.
     - `prompts/architect.md`: add “files‑only” rule + TO USER CLI template; use branch in meta.
     - `prompts/engineer.md`: add “files‑only” rule; forbid CLI for Engineer.
   - Add `theory_api/agents/validate_chat_msgs.py` to validate message files (front matter + header + seq).

CHANGESETS
- `theory_api/agents/validate_chat_meta.py`   # extend JSON Schema (see below)
- `.github/workflows/agents-meta.yml`         # new CI workflow (see below)
- `theory_api/agents/prompts/digital-twin.md` # apply diff below
- `theory_api/agents/prompts/AGENTS.md`       # apply diff below
- `theory_api/agents/prompts/architect.md`    # apply diff below
- `theory_api/agents/prompts/engineer.md`     # apply diff below
- Move & rename templates under `theory_api/agents/templates/` per 5) above
- `theory_api/agents/prompts/communication-protocol.md`  # new rules doc
- `theory_api/agents/prompts/digital-twin.md`            # add files‑only, no CLI
- `theory_api/agents/prompts/architect.md`               # add files‑only, TO USER template
- `theory_api/agents/prompts/engineer.md`                # add files‑only, no CLI
- `theory_api/agents/validate_chat_msgs.py`              # new validator for message files

SCHEMA (validator) — extend properties and required
```python
SCHEMA = {
  "$schema":"https://json-schema.org/draft/2020-12/schema",
  "type":"object",
  "required":["id","slug","area","title","owner","state","branch","created","scope","acceptance","outputs"],
  "properties":{
    "id":{"type":"string","pattern":"^\\d{4}$"},
    "slug":{"type":"string","pattern":"^[a-z0-9-]+$"},
    "area":{"type":"string","enum":["rt","ld","st","ui","dx","ad","dc"]},
    "title":{"type":"string","minLength":3},
    "owner":{"type":"string","enum":["twin","architect","engineer"]},
    "state":{"type":"string","enum":["open","review","merged","closed"]},
    "branch":{"type":"string","pattern":"^(feat|fix|chore)/[a-z]{2}-[a-z0-9-]+-\\d{4}$"},
    "created":{"type":"string","pattern":"^\\d{4}-\\d{2}-\\d{2}T"},
    "scope":{"type":"array","items":{"type":"string"},"minItems":1},
    "non_goals":{"type":"array","items":{"type":"string"}},
    "acceptance":{"type":"array","items":{"type":"string"},"minItems":1},
    "outputs":{"type":"array","items":{"type":"string"},"minItems":1},
    "gh":{
      "type":"object",
      "properties":{
        "sync_mode":{"type":"string","enum":["none","issue-dryrun","issue-live"]},
        "title_pattern":{"type":"string"},
        "labels":{"type":"array","items":{"type":"string"}},
        "issue_body_source":{"type":"string","enum":["SUMMARY.md","META"]}
      },
      "additionalProperties": False
    },
    "ci_gates":{"type":"array","items":{"type":"string"}},
    "notes":{"type":"string"}
  },
  "additionalProperties": False
}
```

GITHUB ACTION (validation + PR title + dry‑run)
```yaml
name: agents-meta
on: [pull_request]
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install pyyaml jsonschema
      - name: Validate meta files
        run: python theory_api/agents/validate_chat_meta.py $(find theory_api/agents/chats -maxdepth 2 -name meta.yaml)
      - name: Check PR title pattern
        env:
          TITLE: ${{ github.event.pull_request.title }}
        run: |
          echo "$TITLE" | grep -Eq '^[0-9]{4} \[[a-z]{2}\] [a-z0-9-]+$' || (echo "PR title must match: 0005 [dx] gh-sync" && exit 1)
      - name: (Dry-run) list chats requesting issue sync
        run: |
          grep -R --line-number "sync_mode: issue-dryrun" theory_api/agents/chats || true
```

PROMPTS — minimal diffs
- `digital-twin.md`:
  - Clarify Twin as preference model; Twin authors meta.yaml; use theory_api/agents/chats paths and branch conventions.
- `AGENTS.md`:
  - Add top note: commit only meta.yaml, SUMMARY.md, DECISION.md; do not commit turns/ dumps/ secrets.
  - Show chats layout; conventions; Twin authors meta.yaml.
  - Merge protocol with CI gates and post‑merge housekeeping.
- `architect.md`:
  - Start from Twin’s meta.yaml; produce 001‑to‑engineer; use branch from meta.
- `engineer.md`:
  - Read meta.yaml + 001; create branch if missing; run acceptance; report STATUS with failing tests before→after.

SMOKE
- `python theory_api/agents/validate_chat_meta.py $(find theory_api/agents/chats -name meta.yaml)`
- `act -j validate` (or push PR) to see CI pass PR‑title + meta‑schema steps
- `make -C theory_api/docs -W html` (docs remain green)
- Ensure template files exist at:
  - `theory_api/agents/templates/meta.template.yaml`
  - `theory_api/agents/templates/decision.template.md`
  - `theory_api/agents/templates/summary.template.md`
- Protocol validators:
  - `python theory_api/agents/validate_chat_msgs.py $(find theory_api/agents/chats -maxdepth 1 -type d)`

RISKS
- None affecting runtime; prompts & CI only.

ASKS
- Create branch `feat/dx-gh-sync-0005`, implement changes, and reply with STATUS + links to CI run and PR.
