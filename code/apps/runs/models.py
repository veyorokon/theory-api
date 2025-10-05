# apps/runs/models.py
import uuid
from django.db import models


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
    ref_slug = models.CharField(max_length=128)  # e.g. "llm_litellm"
    mode = models.CharField(max_length=8)  # "mock" | "real"
    adapter = models.CharField(max_length=8)  # "local" | "modal"
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)

    error_code = models.CharField(max_length=64, null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)

    write_prefix = models.CharField(max_length=512)  # "/artifacts/outputs/{ref_slug}/{run_id}/"
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
            models.Index(fields=["ref_slug", "-started_at"], name="run_ref_started_idx"),
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
