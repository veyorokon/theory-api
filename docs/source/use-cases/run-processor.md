(run-processor)=
# Run Processor

Unified processor execution with support for local Docker runs, hermetic smoke mode, and Modal cloud deployment. This guide mirrors the refactored adapters: we now have two adapters (`local`, `modal`) and a `mode` flag (`default`, `smoke`) that replaces the old mock adapter.

## Quick Start

### Smoke Mode (No External Dependencies)

```bash
cd theory_api/code \
  && python manage.py run_processor \
       --ref llm/litellm@1 \
       --adapter local \
       --mode smoke \
       --inputs-json '{"messages":[{"role":"user","content":"Hello!"}]}' \
       --json
```

Smoke mode runs entirely on the host filesystem—no Docker, MinIO, or provider secrets required. It writes deterministic mock outputs to the chosen `write_prefix`, returning the canonical envelope.

### Local Adapter (Docker Execution)

```bash
# Requires Docker running locally
cd theory_api/code \
  && python manage.py run_processor \
       --ref llm/litellm@1 \
       --adapter local \
       --inputs-json '{"messages":[{"role":"user","content":"Hello!"}],"model":"openai/gpt-4o-mini"}' \
       --json
```

Local default mode launches the processor container using the pinned image digest. Ensure Docker is installed and you have access to the GHCR image referenced in the registry.

### Modal Adapter (Cloud Execution)

```bash
export MODAL_TOKEN_ID="your-token-id"
export MODAL_TOKEN_SECRET="your-token-secret"
export OPENAI_API_KEY="your-key"
cd theory_api/code \
  && python manage.py run_processor \
       --ref llm/litellm@1 \
       --adapter modal \
       --inputs-json '{"messages":[{"role":"user","content":"Hello!"}]}' \
       --json
```

Ensure the pinned image digest is deployed to Modal (see the CI/CD runbook) and that required secrets are available in the target environment.

## Attachments

`run_processor` can materialize local files into artifacts via `$attach` references. Smoke mode supports this without contacting object storage.

```bash
python manage.py run_processor \
  --ref llm/litellm@1 \
  --adapter local \
  --mode smoke \
  --attach image=photo.jpg \
  --inputs-json '{"messages":[{"content":[{"$attach":"image"}]}]}' \
  --json
```

Input snippet after rewriting:

```json
{
  "$artifact": "/artifacts/inputs/b3:abcd.../photo.jpg",
  "cid": "b3:abcd...",
  "mime": "image/jpeg"
}
```

## Command Options

```bash
python manage.py run_processor [options]
```

| Option | Description |
|--------|-------------|
| `--ref` | Processor reference (e.g. `llm/litellm@1`) |
| `--adapter` | `local` (default) or `modal` |
| `--mode` | `default` (real execution) or `smoke` (hermetic mock) |
| `--plan` | Optional plan key for budget tracking |
| `--write-prefix` | Output prefix (must end with `/`), defaults to `/artifacts/outputs/` |
| `--inputs-json` | JSON payload; supports the `schema: v1` format |
| `--adapter-opts-json` | Adapter-specific JSON options |
| `--attach name=path` | Materialize a file into inputs (repeatable) |
| `--json` | Print canonical response envelope |
| `--save-dir` / `--save-first` | Download outputs to the local filesystem |

## Examples

```bash
# Hermetic smoke run (fast unit-style checks)
python manage.py run_processor \
  --ref llm/litellm@1 \
  --adapter local \
  --mode smoke \
  --inputs-json '{"messages":[{"role":"user","content":"What is Theory?"}]}' \
  --json

# Local Docker run with explicit model
python manage.py run_processor \
  --ref llm/litellm@1 \
  --adapter local \
  --inputs-json '{"messages":[{"role":"user","content":"Explain determinism"}],"model":"openai/gpt-4o-mini"}'

# Modal run with attachment
python manage.py run_processor \
  --ref llm/litellm@1 \
  --adapter modal \
  --attach image=photo.jpg \
  --inputs-json '{"messages":[{"content":[{"type":"text","text":"Describe this"},{"$attach":"image"}]}]}' \
  --json
```

## Smoke Mode Inputs Schema

Smoke mode accepts the same `schema: v1` payload; simply set `"mode": "smoke"`:

```json
{
  "schema": "v1",
  "params": {"messages": [{"role": "user", "content": "demo"}]},
  "mode": "smoke"
}
```

## Troubleshooting

- **`mode=smoke` ignored** – ensure you’re not simultaneously passing `--adapter modal` (smoke mode is local-only).
- **Docker missing** – use smoke mode or install Docker before running default local mode.
- **Modal auth errors** – redeploy the processor via the Modal deploy workflow and verify secrets exist (`modal secret list --env <env>`).

For CI details, see the [CI/CD Runbook](../runbooks/ci-cd.md). For adapter internals, see [Registry & Adapters](../concepts/registry-and-adapters.md).
