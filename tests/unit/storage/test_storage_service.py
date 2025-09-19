import io
from unittest.mock import Mock, patch
from django.test import TestCase, override_settings
from django.core.files.base import ContentFile

from apps.storage.service import StorageService
from apps.storage.backends import VendorNeutralStorage


class StorageServiceTests(TestCase):
    """Tests for the storage service"""

    def setUp(self):
        # Reset singleton for each test
        StorageService._instance = None
        StorageService._adapter = None

    @override_settings(STORAGE_BACKEND="minio")
    @patch("apps.storage.service.MinIOAdapter")
    def test_service_uses_minio_adapter(self, mock_minio_adapter):
        """Test service creates MinIO adapter when configured"""
        service = StorageService()
        mock_minio_adapter.assert_called_once()

    @override_settings(STORAGE_BACKEND="s3")
    @patch("apps.storage.service.S3Adapter")
    def test_service_uses_s3_adapter(self, mock_s3_adapter):
        """Test service creates S3 adapter when configured"""
        service = StorageService()
        mock_s3_adapter.assert_called_once()

    @override_settings(STORAGE_BACKEND="invalid")
    def test_service_invalid_backend_raises_error(self):
        """Test service raises error for invalid backend"""
        with self.assertRaises(ValueError) as cm:
            StorageService()
        self.assertIn("Unsupported storage backend: invalid", str(cm.exception))

    def test_service_singleton_behavior(self):
        """Test service implements singleton pattern"""
        service1 = StorageService()
        service2 = StorageService()
        self.assertIs(service1, service2)

    @patch("apps.storage.service.MinIOAdapter")
    def test_service_delegates_upload_file(self, mock_adapter_class):
        """Test service delegates upload_file to adapter"""
        mock_adapter = Mock()
        mock_adapter_class.return_value = mock_adapter
        mock_adapter.upload_file.return_value = "http://example.com/file.txt"

        service = StorageService()
        test_file = io.BytesIO(b"test")

        result = service.upload_file(test_file, "key", "bucket", "text/plain", {"meta": "data"})

        mock_adapter.upload_file.assert_called_once_with(test_file, "key", "bucket", "text/plain", {"meta": "data"})
        self.assertEqual(result, "http://example.com/file.txt")

    @patch("apps.storage.service.MinIOAdapter")
    def test_service_delegates_download_file(self, mock_adapter_class):
        """Test service delegates download_file to adapter"""
        mock_adapter = Mock()
        mock_adapter_class.return_value = mock_adapter
        mock_adapter.download_file.return_value = b"file content"

        service = StorageService()

        result = service.download_file("key", "bucket")

        mock_adapter.download_file.assert_called_once_with("key", "bucket")
        self.assertEqual(result, b"file content")

    @patch("apps.storage.service.MinIOAdapter")
    def test_service_delegates_file_exists(self, mock_adapter_class):
        """Test service delegates file_exists to adapter"""
        mock_adapter = Mock()
        mock_adapter_class.return_value = mock_adapter
        mock_adapter.file_exists.return_value = True

        service = StorageService()

        result = service.file_exists("key", "bucket")

        mock_adapter.file_exists.assert_called_once_with("key", "bucket")
        self.assertTrue(result)

    @patch("apps.storage.service.MinIOAdapter")
    def test_service_delegates_delete_file(self, mock_adapter_class):
        """Test service delegates delete_file to adapter"""
        mock_adapter = Mock()
        mock_adapter_class.return_value = mock_adapter
        mock_adapter.delete_file.return_value = True

        service = StorageService()

        result = service.delete_file("key", "bucket")

        mock_adapter.delete_file.assert_called_once_with("key", "bucket")
        self.assertTrue(result)


class VendorNeutralStorageTests(TestCase):
    """Tests for Django storage backend"""

    def setUp(self):
        self.storage = VendorNeutralStorage("test-bucket")
        self.test_content = b"test file content"
        self.test_name = "test/file.txt"

    @patch("apps.storage.backends.storage_service")
    def test_save_file(self, mock_service):
        """Test file saving"""
        mock_service.upload_file.return_value = "http://example.com/bucket/file.txt"
        content_file = ContentFile(self.test_content, name=self.test_name)

        result = self.storage._save(self.test_name, content_file)

        mock_service.upload_file.assert_called_once()
        self.assertEqual(result, self.test_name)

    @patch("apps.storage.backends.storage_service")
    def test_open_file(self, mock_service):
        """Test file opening"""
        mock_service.download_file.return_value = self.test_content

        file_obj = self.storage._open(self.test_name)

        mock_service.download_file.assert_called_once_with(self.test_name, "test-bucket")
        self.assertEqual(file_obj.read(), self.test_content)

    @patch("apps.storage.backends.storage_service")
    def test_open_file_not_found(self, mock_service):
        """Test opening non-existent file raises error"""
        mock_service.download_file.side_effect = Exception("File not found")

        with self.assertRaises(FileNotFoundError):
            self.storage._open(self.test_name)

    @patch("apps.storage.backends.storage_service")
    def test_exists(self, mock_service):
        """Test file existence check"""
        mock_service.file_exists.return_value = True

        result = self.storage.exists(self.test_name)

        mock_service.file_exists.assert_called_once_with(self.test_name, "test-bucket")
        self.assertTrue(result)

    @patch("apps.storage.backends.storage_service")
    def test_delete(self, mock_service):
        """Test file deletion"""
        mock_service.delete_file.return_value = True

        result = self.storage.delete(self.test_name)

        mock_service.delete_file.assert_called_once_with(self.test_name, "test-bucket")
        self.assertTrue(result)

    @patch("apps.storage.backends.storage_service")
    def test_size(self, mock_service):
        """Test file size retrieval"""
        mock_service.get_file_metadata.return_value = {"size": 1024}

        result = self.storage.size(self.test_name)

        mock_service.get_file_metadata.assert_called_once_with(self.test_name, "test-bucket")
        self.assertEqual(result, 1024)

    @patch("apps.storage.backends.storage_service")
    def test_url(self, mock_service):
        """Test URL generation"""
        expected_url = "https://example.com/bucket/file.txt?signature=abc123"
        mock_service.get_file_url.return_value = expected_url

        result = self.storage.url(self.test_name)

        mock_service.get_file_url.assert_called_once_with(self.test_name, "test-bucket", expires_in=3600)
        self.assertEqual(result, expected_url)

    def test_get_content_type(self):
        """Test content type detection"""
        self.assertEqual(self.storage._get_content_type("file.txt"), "text/plain")
        self.assertEqual(self.storage._get_content_type("image.jpg"), "image/jpeg")
        self.assertEqual(self.storage._get_content_type("video.mp4"), "video/mp4")
        self.assertEqual(self.storage._get_content_type("unknown"), "application/octet-stream")

    @patch("apps.storage.backends.storage_service")
    def test_listdir(self, mock_service):
        """Test directory listing"""
        mock_service.list_files.return_value = ["test/file1.txt", "test/file2.txt", "test/subdir/file3.txt"]

        dirs, files = self.storage.listdir("test/")

        mock_service.list_files.assert_called_once_with("test-bucket", prefix="test/")
        self.assertEqual(dirs, ["subdir"])
        self.assertEqual(files, ["file1.txt", "file2.txt"])


class StorageAdapterConfigurationTests(TestCase):
    """Tests for adapter configuration and initialization"""

    @override_settings(
        STORAGE_BACKEND="minio",
        MINIO_ENDPOINT="localhost:9000",
        MINIO_ACCESS_KEY="testkey",
        MINIO_SECRET_KEY="testsecret",
        MINIO_USE_HTTPS=False,
    )
    @patch("apps.storage.adapters.Minio")
    def test_minio_adapter_configuration(self, mock_minio):
        """Test MinIO adapter uses correct configuration"""
        from apps.storage.adapters import MinIOAdapter

        adapter = MinIOAdapter()

        mock_minio.assert_called_once_with(
            endpoint="localhost:9000", access_key="testkey", secret_key="testsecret", secure=False
        )

    @override_settings(
        STORAGE_BACKEND="s3",
        AWS_ACCESS_KEY_ID="test_key",
        AWS_SECRET_ACCESS_KEY="test_secret",
        AWS_S3_REGION_NAME="us-west-2",
    )
    @patch("apps.storage.adapters.boto3")
    def test_s3_adapter_configuration(self, mock_boto3):
        """Test S3 adapter uses correct configuration"""
        from apps.storage.adapters import S3Adapter

        adapter = S3Adapter()

        mock_boto3.client.assert_called_once_with(
            "s3", aws_access_key_id="test_key", aws_secret_access_key="test_secret", region_name="us-west-2"
        )
