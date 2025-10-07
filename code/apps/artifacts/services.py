"""Artifact services for creating and managing artifacts."""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict
from urllib.parse import quote

from apps.artifacts.models import Artifact
from apps.worlds.models import World
from backend.storage.service import StorageService
from django.conf import settings


class ArtifactService:
    """Service for creating and managing artifacts."""

    @staticmethod
    def create_file_artifact(
        world: World,
        run_id: str,
        key: str,
        content: bytes,
        content_type: str = "application/octet-stream",
    ) -> Artifact:
        """
        Create a file artifact by uploading content to S3.

        Args:
            world: World context
            run_id: Run ID for path scoping
            key: Artifact key (e.g., "messages.jsonl", "document.pdf")
            content: File content bytes
            content_type: MIME type

        Returns:
            Artifact record
        """
        storage = StorageService()
        bucket = settings.STORAGE.get("BUCKET")

        # Generate path and URI
        path = f"{world.id}/{run_id}/{key}"
        uri = f"world://{world.id}/{run_id}/{key}"

        # Upload to storage
        storage.upload_bytes(data=content, key=path, content_type=content_type, bucket=bucket)

        # Get file metadata
        metadata = storage.get_file_metadata(key=path, bucket=bucket)

        # Create artifact record
        artifact = Artifact.objects.create(
            world=world,
            uri=uri,
            path=path,
            data=None,
            is_scalar=False,
            content_type=content_type,
            size_bytes=metadata.get("ContentLength"),
            etag=metadata.get("ETag", "").strip('"'),
            sha256="",  # TODO: compute hash if needed
        )

        return artifact

    @staticmethod
    def create_scalar_artifact(
        world: World,
        run_id: str,
        key: str,
        data: Dict[str, Any],
    ) -> Artifact:
        """
        Create a scalar artifact (inline JSON data).

        Args:
            world: World context
            run_id: Run ID for path scoping
            key: Artifact key
            data: JSON-serializable data

        Returns:
            Artifact record with embedded data in URI
        """
        # Encode data in URI
        encoded_data = quote(json.dumps(data))
        uri = f"world://{world.id}/{run_id}/{key}?data={encoded_data}"

        # Create artifact record
        artifact = Artifact.objects.create(
            world=world,
            uri=uri,
            path="",  # No S3 path for scalars
            data=data,
            is_scalar=True,
            content_type="application/json",
            size_bytes=len(json.dumps(data).encode()),
            etag="",
            sha256="",
        )

        return artifact

    @staticmethod
    def create_inline_artifact(
        world: World,
        run_id: str,
        key: str,
        value: Any,
    ) -> Artifact:
        """
        Create artifact from inline value (auto-detects type).

        Args:
            world: World context
            run_id: Run ID
            key: Artifact key
            value: Value - can be dict/list (JSON) or str/bytes (file)

        Returns:
            Artifact record
        """
        if isinstance(value, (dict, list)):
            # JSON data - create scalar artifact
            return ArtifactService.create_scalar_artifact(world, run_id, key, value)
        elif isinstance(value, str):
            # String - write as JSON file
            content = json.dumps(value).encode()
            return ArtifactService.create_file_artifact(
                world, run_id, f"{key}.json", content, "application/json"
            )
        elif isinstance(value, bytes):
            # Binary - write as file
            return ArtifactService.create_file_artifact(world, run_id, key, value, "application/octet-stream")
        else:
            # Scalar value - create scalar artifact
            return ArtifactService.create_scalar_artifact(world, run_id, key, value)
