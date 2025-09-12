from django.db import models

from apps.plans.models import Plan


class Artifact(models.Model):
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE)
    uri = models.CharField(max_length=512)  # world://artifacts/... path
    content_hash = models.CharField(max_length=128)  # Content fingerprint
    content_type = models.CharField(max_length=128, blank=True)
    size_bytes = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["plan", "uri"], name="uq_artifact_plan_uri")]

    def __str__(self):
        return f"{self.plan.key}:{self.uri}"


class ArtifactSeries(models.Model):
    """Series of related artifacts (e.g., streaming data, chunked files)."""

    plan = models.ForeignKey(Plan, on_delete=models.CASCADE)
    series_key = models.CharField(max_length=256)  # Identifier for the series
    total_chunks = models.PositiveIntegerField(null=True, blank=True)  # Total expected chunks
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["plan", "series_key"], name="uq_artifact_series_plan_key")]
        verbose_name_plural = "Artifact Series"

    def __str__(self):
        return f"{self.plan.key}:{self.series_key}"
