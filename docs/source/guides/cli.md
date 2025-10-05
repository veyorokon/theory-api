# CLI Reference

Command-line interfaces for processor operations: build/registry management, local container runtime, and Modal deployment.

## processorctl - Image & Registry Operations

Manage multi-platform builds, registry pins, and image pushes.

### Build

Build multi-platform images:

```bash
python manage.py processorctl build \
  --ref llm/litellm@1 \
  --platforms linux/amd64,linux/arm64 \
  --json
```

**Parameters:**
- `--ref` (required): Processor reference (e.g. `llm/litellm@1`)
- `--platforms` (optional): Comma-separated list (default: `linux/amd64,linux/arm64`)
- `--json` (optional): JSON output

### Pin

Pin digest for specific platform (explicit platform required):

```bash
python manage.py processorctl pin \
  --ref llm/litellm@1 \
  --platform amd64 \
  --oci ghcr.io/org/image@sha256:abc... \
  --json
```

**Parameters:**
- `--ref` (required): Processor reference
- `--platform` (required): `amd64` or `arm64`
- `--oci` (required): Full OCI digest reference
- `--json` (optional): JSON output

### Push

Push image to registry:

```bash
python manage.py processorctl push \
  --ref llm/litellm@1 \
  --platforms linux/amd64,linux/arm64 \
  --json
```

**Parameters:**
- `--ref` (required): Processor reference
- `--platforms` (optional): Comma-separated list (default: `linux/amd64,linux/arm64`)
- `--json` (optional): JSON output

---

## localctl - Local Container Runtime

Start, stop, and invoke processors in local Docker containers. Secrets injected at start time.

### Start

Start reusable container (secrets injected from environment):

```bash
OPENAI_API_KEY=$OPENAI_API_KEY python manage.py localctl start --ref llm/litellm@1
```

**Parameters:**
- `--ref` (required): Processor reference

**Behavior:**
- Injects secrets from environment variables (defined in `registry.yaml`)
- Fails fast if required secrets missing
- Allocates persistent port stored in `code/.theory/local_ports.json`
- Uses newest build tag or pinned digest from registry

### Run

Invoke processor (container must be started first):

```bash
python manage.py localctl run \
  --ref llm/litellm@1 \
  --mode mock \
  --write-prefix "/artifacts/outputs/test/{execution_id}/" \
  --inputs-json '{"schema":"v1","params":{"messages":[{"role":"user","content":"test"}]}}' \
  --json
```

**Parameters:**
- `--ref` (required): Processor reference
- `--mode` (optional): `mock` (default) or `real`
- `--write-prefix` (optional): Output prefix. Default: `/artifacts/outputs/{ref_slug}/{execution_id}/`
- **JSON Input Options** (mutually exclusive):
  - `--inputs-json` (recommended): Direct JSON input (no escaping required)
  - `--inputs-file PATH`: Read JSON from file
  - `--inputs -`: Read JSON from stdin
- `--json` (optional): JSON output
- `--stream` (optional): Stream WebSocket events

**Mode Behavior:**

| Mode | Effect |
|------|--------|
| `mock` | No external network calls; deterministic outputs via WebSocket |
| `real` | Full container execution with real provider calls |

### Stop

Stop container:

```bash
python manage.py localctl stop --ref llm/litellm@1
```

### Status

View all running containers:

```bash
python manage.py localctl status
```

### Logs

View container logs:

```bash
python manage.py localctl logs --ref llm/litellm@1 --follow
```

**Parameters:**
- `--ref` (required): Processor reference
- `--follow` (optional): Stream logs continuously

### Examples

```bash
# Build-from-source development loop
processorctl build --ref llm/litellm@1 --platforms linux/amd64
localctl start --ref llm/litellm@1
localctl run --ref llm/litellm@1 --mode mock --json

# Pinned digest (supply-chain parity)
processorctl pin --ref llm/litellm@1 --platform amd64 --oci ghcr.io/org/image@sha256:abc...
localctl start --ref llm/litellm@1
localctl run --ref llm/litellm@1 --mode mock --json

# Stop when done
localctl stop --ref llm/litellm@1
```

---

## modalctl - Modal Runtime

Deploy, invoke, and manage processors on Modal. Secrets synced separately.

### Start (Deploy)

Deploy to Modal environment:

```bash
GIT_BRANCH=feat/test GIT_USER=veyorokon \
python manage.py modalctl start \
  --ref llm/litellm@1 \
  --env dev \
  --oci ghcr.io/org/image@sha256:abc...
```

**Parameters:**
- `--ref` (required): Processor reference
- `--env` (required): `dev`, `staging`, or `main`
- `--oci` (required): Full OCI digest reference

**Environment Variables:**
- `GIT_BRANCH` (required for dev): Git branch name
- `GIT_USER` (required for dev): Git username

**Behavior:**
- Dev naming: `{branch}-{user}-{ref_slug}`
- Staging/main naming: `{ref_slug}`
- Deploys WebSocket app to Modal
- Secrets must be synced separately via `sync-secrets`

### Sync Secrets

Sync required secrets to Modal deployment:

```bash
python manage.py modalctl sync-secrets \
  --ref llm/litellm@1 \
  --env dev
```

**Parameters:**
- `--ref` (required): Processor reference
- `--env` (required): `dev`, `staging`, or `main`
- `--fail-on-missing` (optional): Exit with error if secrets missing

**Behavior:**
- Reads secret names from `registry.yaml`
- Syncs from local environment to Modal environment
- Must be run after deployment

### Run

Invoke processor (deployment must exist first):

```bash
python manage.py modalctl run \
  --ref llm/litellm@1 \
  --mode mock \
  --write-prefix "/artifacts/outputs/test/{execution_id}/" \
  --inputs-json '{"schema":"v1","params":{"messages":[{"role":"user","content":"test"}]}}' \
  --json
```

**Parameters:**
- `--ref` (required): Processor reference
- `--mode` (optional): `mock` (default) or `real`
- `--write-prefix` (optional): Output prefix. Default: `/artifacts/outputs/{ref_slug}/{execution_id}/`
- **JSON Input Options** (same as localctl)
- `--json` (optional): JSON output
- `--stream` (optional): Stream WebSocket events

### Stop

Stop Modal deployment:

```bash
python manage.py modalctl stop --ref llm/litellm@1 --env dev
```

### Status

View Modal deployment status:

```bash
python manage.py modalctl status --ref llm/litellm@1 --env dev
```

### Logs

View Modal deployment logs:

```bash
python manage.py modalctl logs --ref llm/litellm@1 --env dev --follow
```

### Verify Digest

Verify deployed digest matches expected:

```bash
python manage.py modalctl verify-digest \
  --ref llm/litellm@1 \
  --env dev \
  --oci ghcr.io/org/image@sha256:abc...
```

### Examples

```bash
# Deploy to dev environment
GIT_BRANCH=feat/test GIT_USER=veyorokon \
modalctl start --ref llm/litellm@1 --env dev --oci ghcr.io/org/image@sha256:abc...

# Sync secrets
modalctl sync-secrets --ref llm/litellm@1 --env dev

# Run processor
modalctl run --ref llm/litellm@1 --mode mock --json

# View logs
modalctl logs --ref llm/litellm@1 --env dev --follow

# Stop when done
modalctl stop --ref llm/litellm@1 --env dev
```

---

## Order of Operations

Standard workflow across both adapters:

1. **Build**: `processorctl build` - Creates multi-platform images
2. **Push**: `processorctl push` - Pushes to registry
3. **Pin**: `processorctl pin` - Updates registry.yaml with digest (explicit --platform required)
4. **Start**: `localctl start` / `modalctl start` - Starts container/deploys function
5. **Secrets**: Injected at start (local) or synced separately (modal)
6. **Run**: `localctl run` / `modalctl run` - Invokes processor

**Key Principles:**
- No auto-starting or auto-building - each command does exactly one thing
- Secrets injected at start time (localctl) or synced separately (modalctl)
- No `--adapter` flag - use `localctl` vs `modalctl` directly
- `write-prefix` defaults to standard: `/artifacts/outputs/{ref_slug}/{execution_id}/`
- All commands accept `--json` for structured output

---

## Storage Backend Configuration

Processors support MinIO (dev) and S3 (prod) via environment variables:

### MinIO (Development)
```bash
# Using canonical minio.local:9000 endpoint
STORAGE_BACKEND=minio \
MINIO_STORAGE_ENDPOINT=minio.local:9000 \
MINIO_STORAGE_ACCESS_KEY=minioadmin \
MINIO_STORAGE_SECRET_KEY=minioadmin \
MINIO_STORAGE_USE_HTTPS=false \
localctl run --ref llm/litellm@1 --mode mock --json
```

### S3 (Production)
```bash
# Using AWS S3 with IAM credentials
STORAGE_BACKEND=s3 \
AWS_ACCESS_KEY_ID=your-access-key-id \
AWS_SECRET_ACCESS_KEY=your-secret-access-key \
ARTIFACTS_BUCKET=theory-artifacts-dev \
ARTIFACTS_REGION=us-east-1 \
localctl run --ref llm/litellm@1 --mode mock --json
```

See {doc}`../apps/storage` for storage adapter details and Terraform setup in `terraform/s3.tf`.

---

## JSON Input Options

All run commands support three mutually exclusive input methods:

- `--inputs-json JSON` - Direct JSON input (recommended, no escaping)
- `--inputs-file PATH` - Read JSON from file (version control friendly)
- `--inputs -` - Read JSON from stdin (heredoc/pipe friendly)

**Benefits:** No shell escaping, IDE syntax highlighting, CI/CD templates, better error messages.

**Example:**
```bash
# Direct JSON
localctl run --ref llm/litellm@1 --inputs-json '{"schema":"v1","params":{...}}'

# From file
localctl run --ref llm/litellm@1 --inputs-file inputs.json

# From stdin
cat inputs.json | localctl run --ref llm/litellm@1 --inputs -
```

---

## Platform Selection

Platform can be overridden for digest selection:

- `--platform` (optional): `amd64` or `arm64`
- Default: `amd64` for modal, host platform for local
- Used for drift validation (matches deployed digest against registry)

**Example:**
```bash
# Force amd64 digest lookup on ARM Mac
localctl run --ref llm/litellm@1 --platform amd64 --mode mock --json
```
