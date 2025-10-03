from django.core.files.storage import Storage
from django.core.files.base import ContentFile
from django.conf import settings
from django.utils.deconstruct import deconstructible

from .service import storage_service


@deconstructible
class VendorNeutralStorage(Storage):
    """
    Django storage backend that uses our vendor-neutral storage service
    """

    def __init__(self, bucket_name=None):
        if bucket_name is None:
            storage = getattr(settings, "STORAGE", {})
            bucket_name = storage.get("BUCKET", "media")
        self.bucket_name = bucket_name

    def _open(self, name, mode="rb"):
        try:
            content = storage_service.download_file(name, self.bucket_name)
            return ContentFile(content)
        except Exception:
            raise FileNotFoundError(f"File {name} not found")

    def _save(self, name, content):
        try:
            # Get content type from file extension
            content_type = self._get_content_type(name)

            # Upload file
            url = storage_service.upload_file(content, name, self.bucket_name, content_type=content_type)
            return name
        except Exception as e:
            raise OSError(f"Error saving file {name}: {e}")

    def exists(self, name):
        return storage_service.file_exists(name, self.bucket_name)

    def delete(self, name):
        return storage_service.delete_file(name, self.bucket_name)

    def size(self, name):
        metadata = storage_service.get_file_metadata(name, self.bucket_name)
        return metadata.get("size", 0)

    def url(self, name):
        """Return public URL for the file"""
        return storage_service.get_file_url(name, self.bucket_name, expires_in=3600)

    def get_accessed_time(self, name):
        # Not supported by most object storage
        raise NotImplementedError()

    def get_created_time(self, name):
        metadata = storage_service.get_file_metadata(name, self.bucket_name)
        return metadata.get("last_modified")

    def get_modified_time(self, name):
        metadata = storage_service.get_file_metadata(name, self.bucket_name)
        return metadata.get("last_modified")

    def listdir(self, path):
        files = storage_service.list_files(self.bucket_name, prefix=path)
        # Split into directories and files
        directories = set()
        files_list = []

        for file_path in files:
            if file_path.startswith(path):
                relative_path = file_path[len(path) :].lstrip("/")
                if "/" in relative_path:
                    directories.add(relative_path.split("/")[0])
                else:
                    files_list.append(relative_path)

        return list(directories), files_list

    def _get_content_type(self, name):
        """Get content type based on file extension"""
        import mimetypes

        content_type, _ = mimetypes.guess_type(name)
        return content_type or "application/octet-stream"
