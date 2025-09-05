# ADR-0001 — Docs as Contracts

- **Status:** Accepted
- **Date:** 2025-09-05  
- **Deciders:** Engineering Team
- **Technical Story:** Documentation framework implementation

## Context

Reference documentation frequently becomes stale and inaccurate:
- Manual documentation drifts from actual implementation
- API docs don't reflect current method signatures  
- Database schemas in docs don't match actual models
- Diagrams become outdated as system evolves
- No enforcement mechanism to catch drift

This creates confusion for developers and reduces documentation trust. Teams stop consulting docs when they can't rely on accuracy.

## Decision

We will implement **Docs as Contracts** where reference content is generated from source of truth:

- **API documentation** generated from docstrings and type hints
- **Database schemas** generated from Django models  
- **Architecture diagrams** generated from code structure
- **Registry documentation** generated from YAML/JSON specifications
- **JSON schemas** exported from model definitions

Generated content lives in `docs/_generated/**` and is never manually edited. CI builds fail if generated content differs from what's committed, preventing drift.

## Consequences

### Positive
- **Documentation never lies** - Generated from actual implementation
- **Automatic updates** - Changes to code automatically update docs  
- **Consistent format** - All API docs follow same structure
- **Comprehensive coverage** - All documented code follows same standards
- **CI enforcement** - Drift is caught automatically in builds

### Negative
- **Build complexity** - Requires docs generation in CI pipeline
- **Contributor friction** - Devs must run generators before committing
- **Limited flexibility** - Generated content can't be customized easily
- **Tool dependencies** - Adds Sphinx, MyST, and other doc tools to build

### Neutral
- **Hybrid approach** - Manual pages for concepts, generated for reference
- **Storage overhead** - Generated files are committed to repository
- **Process change** - Team must adopt new documentation workflow

## Alternatives Considered

### Option A: Pure Manual Documentation
- **Pros:** Full control over content and formatting
- **Cons:** High maintenance burden, inevitable drift
- **Rejected because:** Historical evidence shows manual docs become stale

### Option B: Comments-only Documentation  
- **Pros:** Documentation stays close to code
- **Cons:** Limited formatting, poor discoverability, no cross-references
- **Rejected because:** Insufficient for complex system documentation

### Option C: External Documentation Tools (Notion, GitBook)
- **Pros:** Rich editing experience, collaboration features
- **Cons:** Disconnected from code, still subject to drift
- **Rejected because:** Doesn't solve the core drift problem

## Implementation

1. **Set up Sphinx with MyST** - Markdown-based documentation system
2. **Create docs_export command** - Django management command to generate content
3. **Structure documentation** - Manual concepts + generated reference  
4. **CI integration** - Build docs and check for drift on every PR
5. **Team training** - Onboard developers to new workflow

## Notes

- Implementation demonstrates the pattern with storage app documentation
- Uses existing Django introspection capabilities  
- Follows industry practices from projects like Django REST Framework
- Maintains human-readable source while ensuring accuracy

## Status History

- 2025-09-05: Proposed during documentation framework design
- 2025-09-05: Accepted and implemented with storage app example