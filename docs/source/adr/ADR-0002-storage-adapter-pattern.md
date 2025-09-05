# ADR-0002 — Storage Adapter Pattern

- **Status:** Accepted
- **Date:** 2025-09-05
- **Deciders:** Engineering Team  
- **Technical Story:** Vendor-neutral storage abstraction

## Context

Theory needs file storage that works across different environments:
- **Development**: Local MinIO for fast iteration  
- **Production**: AWS S3 for reliability and scale
- **Testing**: In-memory or local filesystem for speed

Direct coupling to specific storage services creates problems:
- Environment-specific code branches throughout application
- Difficult testing due to external dependencies
- Vendor lock-in makes migration costly  
- Inconsistent interfaces across storage services

## Decision

Implement the **Adapter Pattern** for storage abstraction:

1. **StorageInterface** - Abstract base class defining storage contract
2. **Concrete Adapters** - MinIOAdapter, S3Adapter implementing interface  
3. **StorageService** - Singleton that selects adapter based on configuration
4. **Django Integration** - Custom storage backend using the service

The service automatically switches adapters based on `STORAGE_BACKEND` setting without requiring code changes.

## Consequences  

### Positive
- **Environment transparency** - Same code works in dev/staging/prod
- **Easy testing** - Mock the interface or use test adapters
- **Vendor flexibility** - Can switch storage providers easily
- **Consistent API** - All storage operations use same method signatures  
- **Configuration-driven** - Environment differences handled by settings

### Negative
- **Abstraction overhead** - Extra layer between application and storage
- **Interface constraints** - Must support lowest common denominator features
- **Implementation complexity** - Multiple adapters to maintain
- **Testing burden** - Must test all adapter implementations

### Neutral
- **Singleton service** - Single point of configuration but potential bottleneck
- **Django integration** - Custom storage backend required for file fields
- **Error handling** - Must normalize exceptions across different services

## Alternatives Considered

### Option A: Direct Service Integration
- **Pros:** Simple, direct access to all service features
- **Cons:** Environment-specific code, testing difficulties, vendor lock-in
- **Rejected because:** Creates too much coupling and complexity

### Option B: Configuration-based Service Selection
- **Pros:** No abstraction layer, can use service-specific features  
- **Cons:** Still requires branching logic, difficult to test consistently
- **Rejected because:** Doesn't eliminate the core coupling problem

### Option C: Django-storages Only
- **Pros:** Existing solution, well-tested, supports many backends
- **Cons:** Django-specific, less control over interface, heavyweight
- **Rejected because:** Want custom interface aligned with Theory patterns

## Implementation

```python
# Abstract interface
class StorageInterface(ABC):
    @abstractmethod 
    def upload_file(self, file: BinaryIO, key: str, bucket: str) -> str:
        pass

# Concrete implementations
class MinIOAdapter(StorageInterface): ...
class S3Adapter(StorageInterface): ...

# Service layer
class StorageService:
    def _get_adapter(self) -> StorageInterface:
        backend = settings.STORAGE_BACKEND
        if backend == 's3':
            return S3Adapter()
        elif backend == 'minio': 
            return MinIOAdapter()
```

## Notes

- Implementation includes comprehensive test suite covering all adapters
- Django storage backend enables seamless FileField integration
- Service uses singleton pattern to avoid repeated adapter creation
- Error handling normalizes exceptions across different storage services
- Future adapters (Google Cloud, Azure) can be added easily

## Status History

- 2025-09-05: Proposed during storage system design
- 2025-09-05: Accepted and implemented with MinIO/S3 adapters