import logging
from datetime import timedelta
from typing import Dict, Any, BinaryIO

import boto3
from minio import Minio
from minio.error import S3Error
from django.conf import settings

from .interfaces import StorageInterface

logger = logging.getLogger(__name__)


class MinIOAdapter(StorageInterface):
    """MinIO storage adapter for local development"""

    def __init__(self):
        storage = settings.STORAGE
        minio_config = storage.get("MINIO", {})

        endpoint = minio_config.get("ENDPOINT", "localhost:9000")
        use_https = minio_config.get("USE_HTTPS", False)

        self.client = Minio(
            endpoint=endpoint,
            access_key=minio_config.get("ACCESS_KEY", "minioadmin"),
            secret_key=minio_config.get("SECRET_KEY", "minioadmin"),
            secure=use_https,
        )
        self.base_url = f"{'https' if use_https else 'http'}://{endpoint}"

    def upload_file(
        self,
        file: BinaryIO,
        key: str,
        bucket: str,
        content_type: str | None = None,
        metadata: Dict[str, Any] | None = None,
    ) -> str:
        try:
            # Ensure bucket exists
            if not self.client.bucket_exists(bucket):
                self.client.make_bucket(bucket)

            # Upload file
            file.seek(0)
            self.client.put_object(
                bucket,
                key,
                file,
                length=-1,
                part_size=10 * 1024 * 1024,
                content_type=content_type,
                metadata=metadata or {},
            )
            return f"{self.base_url}/{bucket}/{key}"
        except S3Error as e:
            logger.error(f"MinIO upload error: {e}")
            raise

    def download_file(self, key: str, bucket: str) -> bytes:
        try:
            response = self.client.get_object(bucket, key)
            return response.read()
        except S3Error as e:
            logger.error(f"MinIO download error: {e}")
            raise

    def delete_file(self, key: str, bucket: str) -> bool:
        try:
            self.client.remove_object(bucket, key)
            return True
        except S3Error as e:
            logger.error(f"MinIO delete error: {e}")
            return False

    def get_file_url(self, key: str, bucket: str, expires_in: int = 3600) -> str:
        try:
            return self.client.presigned_get_object(bucket, key, expires=timedelta(seconds=expires_in))
        except S3Error as e:
            logger.error(f"MinIO presigned URL error: {e}")
            raise

    def get_upload_url(self, key: str, bucket: str, expires_in: int = 3600, content_type: str | None = None) -> str:
        try:
            # Ensure bucket exists
            if not self.client.bucket_exists(bucket):
                self.client.make_bucket(bucket)

            # Use canonical hostname (minio.local in dev, reachable by host and containers)
            return self.client.presigned_put_object(bucket, key, expires=timedelta(seconds=expires_in))
        except S3Error as e:
            logger.error(f"MinIO presigned PUT URL error: {e}")
            raise

    def file_exists(self, key: str, bucket: str) -> bool:
        try:
            self.client.stat_object(bucket, key)
            return True
        except S3Error:
            return False

    def list_files(self, bucket: str, prefix: str = "") -> list:
        try:
            objects = self.client.list_objects(bucket, prefix=prefix)
            return [obj.object_name for obj in objects]
        except S3Error as e:
            logger.error(f"MinIO list error: {e}")
            return []

    def get_file_metadata(self, key: str, bucket: str) -> Dict[str, Any]:
        try:
            stat = self.client.stat_object(bucket, key)
            return {
                "size": stat.size,
                "last_modified": stat.last_modified,
                "etag": stat.etag,
                "content_type": stat.content_type,
                "metadata": stat.metadata,
            }
        except S3Error as e:
            logger.error(f"MinIO metadata error: {e}")
            return {}


class S3Adapter(StorageInterface):
    """AWS S3 storage adapter for production"""

    def __init__(self):
        from botocore.config import Config

        storage = settings.STORAGE
        region = storage.get("REGION", "us-east-1")

        config = Config(signature_version="s3v4")
        self.client = boto3.client(
            "s3",
            region_name=region,
            config=config,
        )
        self.region = region

    def upload_file(
        self,
        file: BinaryIO,
        key: str,
        bucket: str,
        content_type: str | None = None,
        metadata: Dict[str, Any] | None = None,
    ) -> str:
        try:
            extra_args = {}
            if content_type:
                extra_args["ContentType"] = content_type
            if metadata:
                extra_args["Metadata"] = metadata

            file.seek(0)
            self.client.upload_fileobj(file, bucket, key, ExtraArgs=extra_args)
            return f"https://{bucket}.s3.{self.region}.amazonaws.com/{key}"
        except Exception as e:
            logger.error(f"S3 upload error: {e}")
            raise

    def download_file(self, key: str, bucket: str) -> bytes:
        try:
            response = self.client.get_object(Bucket=bucket, Key=key)
            return response["Body"].read()
        except Exception as e:
            logger.error(f"S3 download error: {e}")
            raise

    def delete_file(self, key: str, bucket: str) -> bool:
        try:
            self.client.delete_object(Bucket=bucket, Key=key)
            return True
        except Exception as e:
            logger.error(f"S3 delete error: {e}")
            return False

    def get_file_url(self, key: str, bucket: str, expires_in: int = 3600) -> str:
        try:
            return self.client.generate_presigned_url(
                "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=expires_in
            )
        except Exception as e:
            logger.error(f"S3 presigned URL error: {e}")
            raise

    def get_upload_url(self, key: str, bucket: str, expires_in: int = 3600, content_type: str | None = None) -> str:
        try:
            params = {"Bucket": bucket, "Key": key}
            if content_type:
                params["ContentType"] = content_type

            return self.client.generate_presigned_url("put_object", Params=params, ExpiresIn=expires_in)
        except Exception as e:
            logger.error(f"S3 presigned PUT URL error: {e}")
            raise

    def file_exists(self, key: str, bucket: str) -> bool:
        try:
            self.client.head_object(Bucket=bucket, Key=key)
            return True
        except self.client.exceptions.NoSuchKey:
            return False
        except Exception as e:
            # Re-raise non-404 errors (permissions, network, etc.)
            logger.error(f"S3 file_exists error for {bucket}/{key}: {e}")
            raise

    def list_files(self, bucket: str, prefix: str = "") -> list:
        try:
            response = self.client.list_objects_v2(Bucket=bucket, Prefix=prefix)
            return [obj["Key"] for obj in response.get("Contents", [])]
        except Exception as e:
            logger.error(f"S3 list error: {e}")
            return []

    def get_file_metadata(self, key: str, bucket: str) -> Dict[str, Any]:
        try:
            response = self.client.head_object(Bucket=bucket, Key=key)
            return {
                "size": response["ContentLength"],
                "last_modified": response["LastModified"],
                "etag": response["ETag"],
                "content_type": response["ContentType"],
                "metadata": response.get("Metadata", {}),
            }
        except Exception as e:
            logger.error(f"S3 metadata error: {e}")
            return {}
