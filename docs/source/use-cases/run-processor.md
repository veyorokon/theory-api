(run-processor)=
# Run Processor

Execute processors using `localctl` or `modalctl` commands with explicit mode selection.

## Quick Start

### Local Execution

```bash
# Start local container (secrets from environment)
OPENAI_API_KEY=$OPENAI_API_KEY python manage.py localctl start --ref llm/litellm@1

# Run processor
python manage.py localctl run \
  --ref llm/litellm@1 \
  --mode mock \
  --inputs-json '{"schema":"v1","params":{"messages":[{"role":"user","content":"Hello"}]}}' \
  --json

# Stop when done
python manage.py localctl stop --ref llm/litellm@1
```

### Modal Execution

```bash
# Deploy to Modal dev environment
GIT_BRANCH=feat/test GIT_USER=veyorokon \
  python manage.py modalctl start \
    --ref llm/litellm@1 \
    --env dev \
    --oci ghcr.io/org/image@sha256:abc...

# Sync secrets
python manage.py modalctl sync-secrets --ref llm/litellm@1 --env dev

# Run processor
python manage.py modalctl run \
  --ref llm/litellm@1 \
  --mode mock \
  --inputs-json '{"schema":"v1","params":{"messages":[{"role":"user","content":"Hello"}]}}' \
  --json

# Stop when done
python manage.py modalctl stop --ref llm/litellm@1 --env dev
```

## Modes

- **`mock`** (default): Deterministic responses; no external network calls; hermetic execution
- **`real`**: Full container execution with real provider calls; requires secrets

Both modes run in containers via WebSocket protocol. `mode=mock` guarantees determinism and speed; `mode=real` exercises production code paths.

## Attachments

Works identically in both modes and both adapters:

```bash
python manage.py localctl run \
  --ref llm/litellm@1 \
  --mode mock \
  --attach image=photo.jpg \
  --inputs-json '{"schema":"v1","params":{"messages":[{"content":[{"$attach":"image"}]}]}}'
```

## JSON Input Options

Three mutually exclusive input methods:

```bash
# Direct JSON (recommended)
localctl run --ref llm/litellm@1 --inputs-json '{...}'

# From file (version control friendly)
localctl run --ref llm/litellm@1 --inputs-file inputs.json

# From stdin (heredoc/pipe friendly)
cat inputs.json | localctl run --ref llm/litellm@1 --inputs -
```

## Command Reference

### localctl
- `start`: Start container (injects secrets from environment)
- `run`: Invoke processor (container must be running)
- `stop`: Stop container
- `status`: View running containers
- `logs`: View container logs

### modalctl
- `start`: Deploy to Modal environment
- `sync-secrets`: Sync secrets to deployment
- `run`: Invoke processor (deployment must exist)
- `stop`: Stop deployment
- `status`: View deployment status
- `logs`: View deployment logs

## Summary

- Use `localctl` for local Docker execution
- Use `modalctl` for Modal cloud execution
- `mode=mock` for fast, deterministic validation (default)
- `mode=real` for production code paths with external calls
- Secrets injected at start time (localctl) or synced separately (modalctl)
- CI workflows use `mode=mock` for fast validation
- Both adapters produce byte-identical envelopes (determinism parity)
