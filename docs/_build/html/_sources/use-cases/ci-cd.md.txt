# CI/CD & Deployment

**Goal:** Deploy `webapp` to production.

**Transitions:**
- clone → test → build → deploy → healthcheck

**Predicates:** `tests.pass`, `http.200`.

**Adapters:** CLI wrappers (git, pytest, docker, kubectl/modal).

## Scenario

Development team pushes code to the main branch. The system should automatically:
- Clone the latest code
- Run test suite  
- Build container image
- Deploy to production
- Verify deployment health

## Plan Structure

```{mermaid}
graph TD
    A[git-clone] --> B[run-tests]
    B --> C[build-image]
    C --> D[deploy-app] 
    D --> E[health-check]
    
    A --> F[world://artifacts/source/]
    B --> G[world://artifacts/test-results.xml]
    C --> H[world://artifacts/image.tag]
    D --> I[world://artifacts/deployment.yaml]
    E --> J[world://artifacts/health-status.json]
```

## Transitions

### 1. Source Code Checkout

```yaml
id: git-clone
processor_ref: tool:git.clone@1
inputs:
  repository: "https://github.com/company/webapp"
  branch: "main"
  commit_sha: "${trigger.commit_sha}"
write_set:
  - kind: prefix
    path: world://artifacts/source/
predicates:
  success:
    - id: file.exists@1
      args: {path: world://artifacts/source/requirements.txt}
```

### 2. Test Execution

```yaml
id: run-tests
processor_ref: tool:pytest.run@1  
dependencies: [git-clone]
inputs:
  source_dir: world://artifacts/source/
  output_format: "junit"
write_set:
  - kind: exact
    path: world://artifacts/test-results.xml
predicates:
  admission:
    - id: file.exists@1
      args: {path: world://artifacts/source/requirements.txt}
  success:
    - id: tests.pass@1
      args: 
        results_path: world://artifacts/test-results.xml
        min_coverage: 80
```

### 3. Container Build

```yaml
id: build-image
processor_ref: tool:docker.build@1
dependencies: [run-tests]
inputs:
  source_dir: world://artifacts/source/
  dockerfile: "Dockerfile"
  tag: "webapp:${trigger.commit_sha}"
write_set:
  - kind: exact  
    path: world://artifacts/image.tag
predicates:
  admission:
    - id: tests.pass@1
      args: {results_path: world://artifacts/test-results.xml}
  success:
    - id: docker.image_exists@1
      args: {tag: "webapp:${trigger.commit_sha}"}
```

### 4. Production Deployment

```yaml
id: deploy-app
processor_ref: tool:k8s.apply@1
dependencies: [build-image]
inputs:
  manifest_template: world://artifacts/source/k8s/deployment.yaml
  image_tag: "webapp:${trigger.commit_sha}"
  namespace: "production"
write_set:
  - kind: exact
    path: world://artifacts/deployment.yaml
predicates:
  admission:
    - id: docker.image_exists@1
      args: {tag: "webapp:${trigger.commit_sha}"}
  success:
    - id: k8s.deployment_ready@1
      args:
        namespace: "production"
        deployment: "webapp"
```

### 5. Health Verification

```yaml
id: health-check
processor_ref: tool:http.check@1
dependencies: [deploy-app]
inputs:
  endpoint: "https://webapp.company.com/health"
  timeout_s: 30
  retry_count: 5
write_set:
  - kind: exact
    path: world://artifacts/health-status.json
predicates:
  admission:
    - id: k8s.deployment_ready@1
      args:
        namespace: "production" 
        deployment: "webapp"
  success:
    - id: http.get.200@1
      args: 
        url: "https://webapp.company.com/health"
        timeout_ms: 5000
```

## Flow (High Level)

1. **Git webhook triggers** - Push to main branch creates new plan
2. **Source checkout** - Latest code pulled into world artifacts
3. **Test validation** - Full test suite must pass before proceeding
4. **Image building** - Docker container built with commit SHA tag
5. **Deployment** - Kubernetes manifests applied to production
6. **Health verification** - Endpoint checks confirm successful deployment

## Error Handling

### Test Failures
```yaml
on_failure: run-tests
actions:
  - notify_team: "slack://dev-channel" 
  - block_deployment: true
  - create_issue: "github://company/webapp"
```

### Deployment Issues
```yaml
on_failure: deploy-app
actions:
  - rollback_deployment: "previous_version"
  - notify_oncall: "pagerduty://webapp-alerts"
  - preserve_artifacts: ["logs/", "metrics/"]
```

## Monitoring & Observability

All transitions emit detailed events:
- **Build metrics** - Test coverage, build time, image size
- **Deployment progress** - Rollout status, resource usage
- **Health indicators** - Response times, error rates

## Budget Controls

```yaml
budget:
  max_usd_micro: 100000  # $0.10 per deployment
  timeout_s: 1800        # 30 minute max
resources:
  cpu_limit: "2000m"     # 2 CPU cores max
  memory_limit: "4Gi"    # 4GB RAM max
```

```{include} ../../_generated/examples/cicd-dag.md
```