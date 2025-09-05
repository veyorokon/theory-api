# Storage App

Manages vendor-neutral file storage that seamlessly switches between MinIO (development) and S3 (production).

## Purpose

Provide a unified interface for file storage operations while maintaining flexibility to switch between different storage backends based on configuration. This app demonstrates Visureel's adapter pattern in practice.

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

The storage backend is configured via Django settings:

```python
# Development (MinIO)
STORAGE_BACKEND = 'minio'
MINIO_ENDPOINT = 'localhost:9000'
MINIO_ACCESS_KEY = 'minioadmin'
MINIO_SECRET_KEY = 'minioadmin'
MINIO_USE_HTTPS = False

# Production (S3)  
STORAGE_BACKEND = 's3'
AWS_ACCESS_KEY_ID = 'your-access-key'
AWS_SECRET_ACCESS_KEY = 'your-secret-key'
AWS_S3_REGION_NAME = 'us-east-1'
```

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