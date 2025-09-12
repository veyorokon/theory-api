# Modal Deployment & Secrets (Single-Module Flow)

Modal provides serverless execution for processors with pre-deployed functions and centralized secrets. This guide uses a committed module (no codegen, no extra container).

## Secrets Policy

The authoritative secrets standard for Modal integration.

### Core Principle

**Secret names = environment variable names** used by processors, identical across all environments.

### Rules

1. **Per-runtime environment variables**: Create a Modal secret **with the same name** as the environment variable
2. **Registry authentication**: Create **`REGISTRY_AUTH`** containing `REGISTRY_USERNAME` and `REGISTRY_PASSWORD` keys
3. **Same names across environments**: dev/staging/main use identical secret names, only values differ
4. **Code consistency**: Same code runs in all environments without modification

### Required Secrets

| Secret Name | Purpose | Keys | Required |
|-------------|---------|------|----------|
| `REGISTRY_AUTH` | GHCR image pulls | `REGISTRY_USERNAME`, `REGISTRY_PASSWORD` | Yes |
| `OPENAI_API_KEY` | OpenAI API access | `OPENAI_API_KEY` | Yes |
| `LITELLM_API_BASE` | Custom LiteLLM endpoint | `LITELLM_API_BASE` | Optional |

### Secret Creation

**GHCR authentication** (special case: 2 keys in one secret):
```bash
modal secret create REGISTRY_AUTH \
  --from-literal REGISTRY_USERNAME="$GITHUB_USERNAME" \
  --from-literal REGISTRY_PASSWORD="$GITHUB_PAT"
```

**Runtime secrets** (1 secret per environment variable):
```bash
modal secret create OPENAI_API_KEY \
  --from-literal OPENAI_API_KEY="$OPENAI_API_KEY"

modal secret create LITELLM_API_BASE \
  --from-literal LITELLM_API_BASE="$LITELLM_API_BASE"
```

### GitHub Personal Access Token

For `REGISTRY_AUTH`, create a GitHub PAT with:
- **Scope**: `read:packages`
- **Purpose**: Pull container images from GitHub Container Registry (GHCR)
- **Expiration**: Set appropriate expiration policy for your organization

## Deployment Workflow

### Deploy Functions

Deploy committed module and test processor execution:
```bash
cd code
modal deploy --env dev -m modal_app

# Or via Django management command (thin wrapper)
python manage.py sync_modal --env dev
```
Naming in Modal UI is clean and deterministic:
- App: `{slug}-v{ver}-{env}` (e.g., `llm-litellm-v1-dev`)
- Function: `run`

## Environment Isolation

### Modal App

Use a stable app name (default `theory-rt`). Select the environment at deploy/invoke time using `--env` and `environment_name`.

### Secret Isolation

Modal environments provide automatic secret isolation:
- Secrets created in `dev` are not accessible from `staging`
- Same secret names, different values per environment
- No code changes required between environments

## Registry Integration

### Image Digests

Processors reference specific image digests from registry YAML:

```yaml
# code/apps/core/registry/processors/llm_litellm.yaml
name: llm/litellm@1
image:
  oci: ghcr.io/veyorokon/llm_litellm@sha256:09e1fb31078db18369fa50c393ded009c88ef880754dbfc1131d750ce3f8f225
```

### Secret Requirements

Registry YAML defines required secrets:

```yaml
secrets:
  required: [OPENAI_API_KEY]
```

Optional secrets (like `LITELLM_API_BASE`) can be present but are not required for function deployment.

## Troubleshooting

### Common Issues

**"invalid username/password" during deploy:**
- Verify `REGISTRY_AUTH` secret exists
- Check GitHub PAT has `read:packages` scope
- Ensure PAT hasn't expired

**"function not found" during execution:**
- Ensure deployment ran to the correct environment (`--env dev|staging|main`).
- App name is `{slug}-v{ver}-{env}`; function name is `run`.
- Re-deploy committed module: `cd code && modal deploy --env <env> -m modal_app`.

**"403 forbidden" on secret access:**
- Secret name must match environment variable name exactly
- Verify secret exists in correct Modal environment
- Check Modal environment permissions

**"image pull failed":**
- Verify GHCR image exists and is accessible
- Check `REGISTRY_AUTH` credentials are valid
- Ensure image digest in registry YAML is correct

### Debug Commands

**List deployed apps/functions:**
```bash
modal app list --env dev
modal function list --app llm-litellm-v1-dev --env dev
```

**Check secret existence:**
```bash
modal secret list
```

**View function logs:**
```bash
modal logs --app llm-litellm-v1-dev --env dev
```

## Performance Considerations

### Warm Pool Management

- Pre-deployed functions maintain warm pools
- GPU functions benefit most from warm starts
- Function idle timeout affects warm pool retention

### Resource Allocation

Configure resources in registry YAML:

```yaml
runtime:
  cpu: "2"
  memory_gb: 4
  timeout_s: 300
```

Higher resource allocations may reduce cold start frequency but increase costs.

### Concurrent Execution

Modal automatically scales functions based on demand:
- No manual scaling configuration required
- Concurrent executions share warm pools when possible
- Different profiles create separate function instances

## Security Best Practices

### Secret Management

1. **Rotate secrets regularly**: Update GitHub PATs and API keys periodically
2. **Principle of least privilege**: Only grant necessary scopes to tokens
3. **Environment isolation**: Use separate secrets for dev/staging/main
4. **Audit access**: Monitor secret usage in Modal dashboard

### Image Security

1. **Pin specific digests**: Always use SHA256 digests, not tags
2. **Scan images**: Use security scanning on processor images
3. **Minimal base images**: Reduce attack surface in processor containers
4. **Regular updates**: Keep base images and dependencies current

## Cross-References

- {doc}`cli` - CLI commands for Modal deployment (`sync_modal`, `run_processor`)
- {doc}`../concepts/adapters` - Modal adapter implementation details
- {doc}`../reference/configuration` - Complete secrets standard reference
- [ADR-0015: Local Adapter Docker Execution](../adr/ADR-0015-local-adapter-docker-execution.md) - Docker execution patterns that inform Modal design
