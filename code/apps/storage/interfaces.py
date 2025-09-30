from abc import ABC, abstractmethod
from typing import Dict, Any, BinaryIO


class StorageInterface(ABC):
    """Abstract base class for storage adapters"""

    @abstractmethod
    def upload_file(
        self,
        file: BinaryIO,
        key: str,
        bucket: str,
        content_type: str | None = None,
        metadata: Dict[str, Any] | None = None,
    ) -> str:
        """Upload a file and return the public URL"""
        pass

    @abstractmethod
    def download_file(self, key: str, bucket: str) -> bytes:
        """Download a file and return its contents"""
        pass

    @abstractmethod
    def delete_file(self, key: str, bucket: str) -> bool:
        """Delete a file and return success status"""
        pass

    @abstractmethod
    def get_file_url(self, key: str, bucket: str, expires_in: int = 3600) -> str:
        """Get a presigned URL for downloading the file"""
        pass

    @abstractmethod
    def get_upload_url(
        self, key: str, bucket: str, expires_in: int = 3600, content_type: str | None = None, audience: str = "host"
    ) -> str:
        """Get a presigned URL for uploading a file

        Args:
            audience: The context where the URL will be used ("host", "container", "modal")
        """
        pass

    @abstractmethod
    def file_exists(self, key: str, bucket: str) -> bool:
        """Check if a file exists"""
        pass

    @abstractmethod
    def list_files(self, bucket: str, prefix: str = "") -> list:
        """List files in a bucket with optional prefix"""
        pass

    @abstractmethod
    def get_file_metadata(self, key: str, bucket: str) -> Dict[str, Any]:
        """Get file metadata"""
        pass
