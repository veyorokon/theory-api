from django.conf import settings
from .adapters import MinIOAdapter, S3Adapter
from .interfaces import StorageInterface


class StorageService:
    """
    Vendor-neutral storage service that automatically switches between 
    MinIO (development) and S3 (production) based on configuration
    """
    
    _instance = None
    _adapter = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._adapter is None:
            self._adapter = self._get_adapter()
    
    def _get_adapter(self) -> StorageInterface:
        """Factory method to get the appropriate storage adapter"""
        storage_backend = getattr(settings, 'STORAGE_BACKEND', 'minio').lower()
        
        if storage_backend == 's3':
            return S3Adapter()
        elif storage_backend == 'minio':
            return MinIOAdapter()
        else:
            raise ValueError(f"Unsupported storage backend: {storage_backend}")
    
    @property
    def adapter(self) -> StorageInterface:
        return self._adapter
    
    # Delegate all interface methods to the adapter
    def upload_file(self, file, key, bucket, content_type=None, metadata=None):
        return self.adapter.upload_file(file, key, bucket, content_type, metadata)
    
    def download_file(self, key, bucket):
        return self.adapter.download_file(key, bucket)
    
    def delete_file(self, key, bucket):
        return self.adapter.delete_file(key, bucket)
    
    def get_file_url(self, key, bucket, expires_in=3600):
        return self.adapter.get_file_url(key, bucket, expires_in)
    
    def file_exists(self, key, bucket):
        return self.adapter.file_exists(key, bucket)
    
    def list_files(self, bucket, prefix=""):
        return self.adapter.list_files(bucket, prefix)
    
    def get_file_metadata(self, key, bucket):
        return self.adapter.get_file_metadata(key, bucket)
    
    def upload_bytes(self, data, key, content_type='application/json', bucket='default', metadata=None):
        """Upload bytes data as a file. Convenience wrapper around upload_file."""
        import io
        return self.upload_file(
            file=io.BytesIO(data), 
            key=key, 
            bucket=bucket, 
            content_type=content_type, 
            metadata=metadata
        )


# Singleton instance
storage_service = StorageService()