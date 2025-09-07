# Communication Protocol

## Core Rule: Files-Only Messaging

All inter-agent communication MUST be conducted through files in the chat directory. No agent-to-agent messages via CLI output.

## Directory Structure
```
theory_api/agents/chats/<id>-<area>-<slug>/
  meta.yaml                 # Twin-authored contract
  001-to-engineer.md        # Architect → Engineer
  002-to-architect.md       # Engineer → Architect  
  003-to-engineer.md        # Architect → Engineer
  ...
  SUMMARY.md               # Added on close
  DECISION.md              # Final decision
```

## Message File Format

### Filename Convention
`<seq>-to-<role>.md`
- `seq`: Zero-padded 3-digit sequence (001, 002, 003...)
- `role`: Target role (engineer, architect, twin)

### Required Structure
```markdown
---
from: architect|engineer|twin
to: architect|engineer|twin
chat: XXXX-area-slug
seq: XXX
ts: 2025-XX-XXTXX:XX:XXZ
purpose: Brief description of message intent
---

-- TO <ROLE>:

[Message content following role-specific template]
```

## Role-Specific Rules

### Digital Twin
- **MUST**: Author meta.yaml for each chat
- **MUST**: Use files-only messaging
- **MUST NOT**: Print to CLI
- **Template**: STATUS → PLAN → CHANGESETS → SMOKE → RISKS

### Architect
- **MUST**: Read Twin's meta.yaml before starting
- **MUST**: Create 001-to-engineer.md as first message
- **MUST**: Use branch specified in meta.yaml
- **MAY**: Use CLI for TO USER messages with this template:
  ```
  TO USER:
  STATUS: [Brief status]
  ACTION NEEDED: [What user should do]
  CONTEXT: [Link to chat directory]
  ```
- **Template**: STATUS → PLAN → CHANGESETS → SMOKE → RISKS → ASKS

### Engineer
- **MUST**: Read meta.yaml + latest message before responding
- **MUST**: Create/use branch from meta.yaml
- **MUST**: Run acceptance criteria from meta.yaml
- **MUST NOT**: Print to CLI
- **Template**: STATUS → OBSERVATIONS → ANALYSIS → GATES → PLAN → CHANGESETS → DOCS → SMOKE → RISKS → ASKS

## Message Sequencing

1. Messages are numbered sequentially starting from 001
2. Each role responds with the next sequence number
3. Do not edit previous messages
4. Do not skip sequence numbers
5. Update meta.yaml.owner after sending a message

## Validation

Messages are validated by `theory_api/agents/validate_chat_msgs.py`:
- YAML front matter is parseable and complete
- Sequence numbers are consecutive
- Target role header matches filename
- Timestamps are ISO 8601 format

## CI Integration

GitHub Actions validate:
- All meta.yaml files against schema
- PR titles match pattern: `XXXX [area] slug`
- Message files follow protocol
- No direct CLI output in logs from Twin/Engineer

## Exceptions

The only permitted CLI output:
1. Architect TO USER messages (with required template)
2. Tool execution output (bash commands, file operations)
3. Error messages from failed operations

## Migration Path

Existing chats without front matter:
1. Are grandfathered as-is
2. New messages in those chats should follow protocol
3. Full migration happens at chat closure