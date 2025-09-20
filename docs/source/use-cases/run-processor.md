(run-processor)=
# Run Processor

Unified processor execution with explicit mode selection.

## Quick Start

```bash
cd theory_api/code && python manage.py run_processor \
  --ref llm/litellm@1 \
  --adapter local \
  --mode mock \
  --inputs-json '{"schema":"v1","params":{"messages":[{"role":"user","content":"Hello"}]}}' \
  --json
```

`mode=mock` runs hermetically on the host (no Docker, no external services). Switch to `--mode real` to exercise the full container path.

## Attachments

Works identically in both modes:

```bash
python manage.py run_processor \
  --ref llm/litellm@1 \
  --adapter local \
  --mode mock \
  --attach image=photo.jpg \
  --inputs-json '{"schema":"v1","params":{"messages":[{"content":[{"$attach":"image"}]}]}}'
```

## Summary

- `adapter`: `local` or `modal`
- `mode`: `mock` (default) or `real`
- Fire-and-forget smoke tests by forcing `mode=mock`
- CI workflows use `mode=mock` for fast validation; deploy workflows smoke Modal with `mode=mock`
