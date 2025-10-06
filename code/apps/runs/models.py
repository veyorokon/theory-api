# apps/runs/models.py
import uuid
from django.db import models
from django.utils import timezone


class Run(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending"
        RUNNING = "running"
        SUCCEEDED = "succeeded"
        FAILED = "failed"
        PREEMPTED = "preempted"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)  # run_id

    world = models.ForeignKey("worlds.World", on_delete=models.CASCADE, related_name="runs")
    caller_agent = models.ForeignKey("agents.Agent", on_delete=models.PROTECT, related_name="runs_initiated")
    plan = models.ForeignKey("plans.Plan", on_delete=models.SET_NULL, null=True, blank=True, related_name="runs")
    goal = models.ForeignKey("goals.Goal", on_delete=models.SET_NULL, null=True, blank=True, related_name="runs")

    ref = models.CharField(max_length=128)  # e.g. "llm/litellm@1"
    mode = models.CharField(max_length=8)  # "mock" | "real"
    adapter = models.CharField(max_length=8)  # "local" | "modal"
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)

    error_code = models.CharField(max_length=64, null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)

    write_prefix = models.CharField(max_length=512)  # "/{world_id}/{run_id}/"
    index_path = models.CharField(max_length=512, blank=True)  # set on settle - outputs.json

    image_digest_expected = models.CharField(max_length=71, null=True, blank=True)  # "sha256:…"
    image_digest_actual = models.CharField(max_length=71, null=True, blank=True)
    drift_ok = models.BooleanField(default=True)

    meta = models.JSONField(default=dict)  # envelope.meta snapshot
    inputs = models.JSONField(default=dict)  # redacted input snapshot (for audit)

    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    cost_micro = models.BigIntegerField(default=0)  # total micro-dollars
    usage = models.JSONField(null=True, blank=True)  # e.g. {"tokens_in":..., "tokens_out":...}

    class Meta:
        indexes = [
            models.Index(fields=["world", "-started_at"], name="run_world_started_idx"),
            models.Index(fields=["goal", "-started_at"], name="run_goal_started_idx"),
            models.Index(fields=["plan", "-started_at"], name="run_plan_started_idx"),
            models.Index(fields=["ref", "-started_at"], name="run_ref_started_idx"),
        ]
        ordering = ["-started_at"]

    def __str__(self):
        return f"Run({self.id}) {self.ref} [{self.status}]"

    # Convenience
    @property
    def succeeded(self) -> bool:
        return self.status == self.Status.SUCCEEDED

    @property
    def duration_ms(self) -> int:
        if self.started_at and self.ended_at:
            return (self.ended_at - self.started_at).total_seconds() * 1000
        return 0

    @property
    def duration_sec(self) -> int:
        return self.duration_ms // 1000

    @property
    def duration_min(self) -> int:
        return self.duration_sec // 60

    def finalize(self, envelope: dict) -> None:
        """Update run from terminal envelope (status, meta, outputs)."""
        from apps.artifacts.models import Artifact

        self.status = envelope.get("status", self.Status.FAILED)
        self.meta = envelope.get("meta", {})
        self.index_path = envelope.get("index_path", "")
        self.ended_at = timezone.now()

        # Extract error details if present
        if "error" in envelope:
            error = envelope["error"]
            self.error_code = error.get("code", "")
            self.error_message = error.get("message", "")

        # Extract cost if available
        if "cost_micro" in envelope.get("meta", {}):
            self.cost_micro = envelope["meta"]["cost_micro"]

        self.save()

        # Create Artifact + RunArtifact records for each output
        outputs = envelope.get("outputs", [])
        for output in outputs:
            path = output["path"].lstrip("/")  # Remove leading slash
            key = path.split("/")[-1].rsplit(".", 1)[0]  # Extract key from path
            uri = f"world://{self.world.id}/{self.id}/{path}"

            # Create or get Artifact
            artifact, created = Artifact.objects.get_or_create(
                world=self.world,
                uri=uri,
                defaults={
                    "path": f"{self.world.id}/{self.id}/{path}",
                    "data": None,
                    "is_scalar": False,
                    "content_type": output.get("content_type", ""),
                    "size_bytes": output.get("size"),
                    "etag": output.get("etag", "").strip('"'),
                    "sha256": output.get("sha256", ""),
                }
            )

            # Link to run as output
            RunArtifact.objects.create(
                run=self,
                artifact=artifact,
                direction=RunArtifact.DIRECTION_OUT,
                key=key,
            )

            # Also create legacy RunOutput for backwards compat (temporary)
            RunOutput.objects.create(
                run=self,
                key=key,
                uri=uri,
                path=path,
                content_type=output.get("content_type", ""),
                size_bytes=output.get("size"),
                etag=output.get("etag", ""),
                sha256=output.get("sha256", ""),
            )


class RunArtifact(models.Model):
    """
    Links a Run to an Artifact with direction and key.

    Direction indicates whether artifact was an input or output.
    Key identifies the semantic role (e.g., "messages", "document", "summary").
    """

    DIRECTION_IN = "in"
    DIRECTION_OUT = "out"
    DIRECTION_CHOICES = [
        (DIRECTION_IN, "Input"),
        (DIRECTION_OUT, "Output"),
    ]

    run = models.ForeignKey(Run, on_delete=models.CASCADE, related_name="artifacts")
    artifact = models.ForeignKey("artifacts.Artifact", on_delete=models.CASCADE, related_name="run_links")
    direction = models.CharField(max_length=3, choices=DIRECTION_CHOICES)
    key = models.CharField(max_length=128)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "run_artifact"
        unique_together = [("run", "direction", "key")]
        indexes = [
            models.Index(fields=["run", "direction"]),
            models.Index(fields=["artifact"]),
        ]
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.run.id}:{self.direction}:{self.key}"


# Legacy model - to be removed after migration
class RunOutput(models.Model):
    """Tracks one file artifact produced by a Run."""

    run = models.ForeignKey(Run, on_delete=models.CASCADE, related_name="outputs")
    key = models.CharField(max_length=128)  # matches ToolIO.key
    uri = models.CharField(max_length=512)  # world://artifacts/outputs/{ref_slug}/{run_id}/...
    path = models.CharField(max_length=256)  # Relative path (e.g., outputs/text/response.txt)
    content_type = models.CharField(max_length=128, blank=True)
    size_bytes = models.BigIntegerField(null=True, blank=True)
    etag = models.CharField(max_length=128, blank=True)
    sha256 = models.CharField(max_length=64, blank=True)

    class Meta:
        unique_together = [("run", "key")]
        indexes = [
            models.Index(fields=["run", "key"]),
            models.Index(fields=["uri"]),
        ]

    def __str__(self):
        return f"{self.run_id}:{self.key}"
