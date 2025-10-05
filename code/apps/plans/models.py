# apps/plans/models.py
from __future__ import annotations
from django.db import models
from django.utils import timezone


class Plan(models.Model):
    """
    A static DAG/spec describing *how* to achieve a Goal.
    Multiple Plans can exist per Goal; a Plan can be re-run many times.
    """

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("ready", "Ready"),
        ("running", "Running"),
        ("succeeded", "Succeeded"),
        ("failed", "Failed"),
        ("abandoned", "Abandoned"),
    ]

    id = models.BigAutoField(primary_key=True)

    # Scope
    world = models.ForeignKey("worlds.World", on_delete=models.CASCADE, related_name="plans")
    goal = models.ForeignKey("goals.Goal", on_delete=models.CASCADE, related_name="plans")

    # Identity & metadata
    key = models.CharField(max_length=128)  # human-friendly key, unique per world
    title = models.CharField(max_length=256, blank=True, default="")
    description = models.TextField(blank=True, default="")

    # Static plan graph & defaults (DAG of tool nodes + edges)
    spec = models.JSONField(default=dict)  # e.g., {"nodes":[{ref,params,...}], "edges":[...]}
    defaults = models.JSONField(default=dict)  # param defaults / macros applied at run start

    # Accounting (micro-cents/dollars depending on your unit; we’re using micro-dollar)
    budget_micro = models.BigIntegerField(default=0)  # allowed
    spent_micro = models.BigIntegerField(default=0)  # observed

    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="draft")

    # Audit
    created_by = models.ForeignKey("agents.Agent", on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("world", "key")]
        indexes = [
            models.Index(fields=["world", "goal"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:
        return f"{self.world_id}:{self.key}"
