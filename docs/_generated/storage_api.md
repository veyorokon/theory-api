# Storage API Documentation

## Architecture Diagram

```{mermaid}
graph TD
    Client[Client Code]
    Service[StorageService<br/>Singleton]
    Interface[StorageInterface<br/>ABC]
    MinIO[MinIOAdapter]
    S3[S3Adapter]
    Backend[Django Storage Backend]
    
    Client --> Service
    Backend --> Service
    Service --> Interface
    Interface <|-- MinIO
    Interface <|-- S3
    
    Service -.->|Development| MinIO
    Service -.->|Production| S3
    
    style Interface fill:#f9f,stroke:#333,stroke-width:2px
    style Service fill:#bbf,stroke:#333,stroke-width:2px
```

## StorageInterface

Abstract base class for storage adapters.

### Methods

#### `delete_file(self, key: str, bucket: str) -> bool`

Delete a file and return success status

#### `download_file(self, key: str, bucket: str) -> bytes`

Download a file and return its contents

#### `file_exists(self, key: str, bucket: str) -> bool`

Check if a file exists

#### `get_file_metadata(self, key: str, bucket: str) -> Dict[str, Any]`

Get file metadata

#### `get_file_url(self, key: str, bucket: str, expires_in: int = 3600) -> str`

Get a presigned URL for the file

#### `list_files(self, bucket: str, prefix: str = '') -> list`

List files in a bucket with optional prefix

#### `upload_file(self, file: <class 'BinaryIO'>, key: str, bucket: str, content_type: str | None = None, metadata: Optional[Dict[str, Any]] = None) -> str`

Upload a file and return the public URL


## StorageService

Vendor-neutral storage service (Singleton pattern).

```python
from apps.storage.service import storage_service
# Automatically uses MinIO in dev, S3 in prod
url = storage_service.upload_file(file, key, bucket)
```


## Adapters

### MinIOAdapter

Local development storage using MinIO.

### S3Adapter

Production storage using AWS S3.
