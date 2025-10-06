# apps/artifacts/models.py
"""
Artifact models for universal storage of run inputs and outputs.

Design principles:
- One Artifact record per unique file in storage
- Deduplication via sha256 hash
- World-scoped URIs for security
- RunArtifact links artifacts to runs with direction (in/out)
"""

from __future__ import annotations

import uuid
from django.db import models


class Artifact(models.Model):
    """
    Universal artifact - files in S3 or scalar values.

    Design:
    - Files: path points to S3, data is null, is_scalar=False
    - Scalars: data contains JSON, path is empty, is_scalar=True
    - URI format for scalars: world://{world}/{run}/key?data={json}
    - One record per artifact, deduped by world+path or world+uri
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    world = models.ForeignKey("worlds.World", on_delete=models.CASCADE, related_name="artifacts")

    # Universal storage
    uri = models.CharField(max_length=1024, db_index=True)  # Always looks like a URI - may need to be a property if too large
    path = models.CharField(max_length=512, blank=True)  # S3 key (empty for scalars)
    data = models.JSONField(null=True, blank=True)  # Inline data for scalars, null for files
    is_scalar = models.BooleanField(default=False)

    # Content metadata
    content_type = models.CharField(max_length=128, blank=True)
    size_bytes = models.BigIntegerField(null=True, blank=True)
    sha256 = models.CharField(max_length=64, blank=True, db_index=True)
    etag = models.CharField(max_length=128, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "artifact"
        # Can't use unique_together on path since scalars have empty path
        # Use unique constraint on uri instead
        constraints = [
            models.UniqueConstraint(fields=["world", "uri"], name="artifact_world_uri_unique"),
        ]
        indexes = [
            models.Index(fields=["world", "path"]),  # For file lookups
            models.Index(fields=["world", "sha256"]),  # Dedup queries
            models.Index(fields=["world", "-created_at"]),
            models.Index(fields=["world", "is_scalar"]),  # Filter scalars vs files
        ]
        ordering = ["-created_at"]

    def __str__(self):
        scalar_flag = " [scalar]" if self.is_scalar else ""
        return f"Artifact({self.uri}){scalar_flag}"
