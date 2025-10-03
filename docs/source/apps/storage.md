# Storage App

Manages vendor-neutral file storage that seamlessly switches between MinIO (development) and S3 (production).

## Purpose

Provide a unified interface for file storage operations while maintaining flexibility to switch between different storage backends based on configuration. This app demonstrates Theory's adapter pattern in practice.

## Data Model & API

```{automodule} apps.storage.interfaces
:members:
```

```{automodule} apps.storage.service
:members:
```

```{automodule} apps.storage.adapters
:members:
```

```{automodule} apps.storage.backends
:members:
```

## Architecture (Generated)

```{include} ../../_generated/storage_api.md
```

## Configuration

The storage backend is configured via environment variables and Django settings:

### Development (MinIO)

```bash
# Environment variables
export STORAGE_BACKEND=minio
export MINIO_STORAGE_ENDPOINT=minio.local:9000
export MINIO_STORAGE_ACCESS_KEY=minioadmin
export MINIO_STORAGE_SECRET_KEY=minioadmin
export MINIO_STORAGE_USE_HTTPS=false
```

**Canonical MinIO endpoint**: `minio.local:9000` works from both host and Docker containers via:
- Docker Compose: `--add-host minio.local:host-gateway` in service definitions
- Host: `/etc/hosts` entry `127.0.0.1 minio.local`

### Production (S3)

```bash
# Environment variables
export STORAGE_BACKEND=s3
export AWS_ACCESS_KEY_ID=your-access-key-id
export AWS_SECRET_ACCESS_KEY=your-secret-access-key
export ARTIFACTS_BUCKET=theory-artifacts-dev
export ARTIFACTS_REGION=us-east-1
```

### Terraform Infrastructure (S3)

The S3 backend is provisioned via Terraform in `terraform/s3.tf`:

```bash
# Initialize Terraform (first time only)
cd terraform
terraform init -backend-config=backend-local.hcl

# Plan infrastructure changes
terraform plan

# Apply changes (creates S3 bucket + IAM user)
terraform apply
```

**Resources created**:
- S3 bucket: `theory-artifacts-dev` (versioning enabled, encryption at rest)
- IAM user: `theory-signer-dev` (least-privilege policy for presigned URLs)
- Access credentials output for use in Django settings

See `terraform/s3.tf` for full infrastructure definition and {doc}`../../source/adr/ADR-0002-storage-adapter-pattern` for design rationale.

## Usage Examples

### Basic Operations

```python
from apps.storage.service import storage_service
import io

# Upload a file
file_data = io.BytesIO(b"Hello, World!")
url = storage_service.upload_file(
    file=file_data,
    key="documents/hello.txt",
    bucket="my-bucket",
    content_type="text/plain"
)

# Download file
content = storage_service.download_file("documents/hello.txt", "my-bucket")

# Check existence
exists = storage_service.file_exists("documents/hello.txt", "my-bucket")
```

### Presigned URLs for Processor Outputs

Processors use presigned PUT URLs to upload outputs directly to storage:

```python
from apps.storage.service import storage_service

# Generate presigned PUT URL (orchestrator-side)
put_url = storage_service.get_upload_url(
    bucket="theory-artifacts-dev",
    key="artifacts/llm/litellm/1/exec-123/outputs/text/response.txt",
    expires_in=900,  # 15 minutes
    content_type="text/plain"
)

# Processor uses this URL to PUT content
# PUT https://theory-artifacts-dev.s3.us-east-1.amazonaws.com/artifacts/...?X-Amz-...
# Content-Type: text/plain
# Body: <output content>
```

See {doc}`../guides/processor-outputs` for output index structure and {doc}`../concepts/envelopes-and-index` for envelope format.

### Django Integration

```python
# In models.py
from django.db import models

class Document(models.Model):
    title = models.CharField(max_length=200)
    file = models.FileField(upload_to='documents/')  # Uses storage backend
    created_at = models.DateTimeField(auto_now_add=True)
```

## Invariants

- All adapters implement the complete StorageInterface
- Service layer maintains singleton pattern
- Backend switching is transparent to calling code
- File operations are atomic where possible
- Errors are properly propagated with context

## Testing

Run the comprehensive test suite:
```bash
python manage.py test apps.storage
```

Tests cover:
- Interface compliance for all adapters
- Service layer functionality
- Django storage backend integration
- Error handling and edge cases

## Runbooks

### Adding a New Adapter

1. Create adapter class inheriting from `StorageInterface`
2. Implement all abstract methods
3. Add configuration handling in settings
4. Update service factory method
5. Add comprehensive tests
6. Update documentation

### Debugging Storage Issues

1. Check configuration in Django settings
2. Verify network connectivity to storage service
3. Check credentials and permissions
4. Review logs for specific error messages
5. Test with minimal reproduction case
