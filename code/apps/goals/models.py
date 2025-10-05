# apps/worlds/models.py (or apps/goals/models.py if you prefer)
from django.conf import settings
from django.db import models


class Goal(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"  # declared, not being worked
        ACTIVE = "active", "Active"  # has (or will have) plans/runs
        SATISFIED = "satisfied", "Satisfied"  # predicate held true at satisfied_at
        FAILED = "failed", "Failed"  # abandoned or impossible
        CANCELLED = "cancelled", "Cancelled"  # user/system cancelled

    # Scope & identity
    world = models.ForeignKey("worlds.World", on_delete=models.CASCADE, related_name="goals")
    predicate_tool = models.ForeignKey(
        "tools.Tool", on_delete=models.PROTECT, related_name="goals_using_predicate", null=True, blank=True
    )
    key = models.SlugField(max_length=128)  # stable identifier within a world (e.g., "video-2025-q4")
    title = models.CharField(max_length=256, blank=True)
    description = models.TextField(blank=True)

    # Hierarchy (subgoals)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="children")
    # Lifecycle
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    priority = models.PositiveIntegerField(null=True, blank=True)  # optional ordering hint

    # Audit
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="created_goals"
    )
    satisfied_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    # Free-form extras
    labels = models.JSONField(null=True, blank=True)  # small dict/list of tags
    meta = models.JSONField(null=True, blank=True)  # lightweight annotations

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (("world", "key"),)
        indexes = [
            models.Index(fields=["world", "status"]),
            models.Index(fields=["parent"]),
        ]
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.world_id}:{self.key}"

    # Small helpers (no re-eval logic yet)
    def mark_satisfied(self, ts):
        self.status = self.Status.SATISFIED
        self.satisfied_at = ts

    def mark_failed(self, ts):
        self.status = self.Status.FAILED
        self.failed_at = ts

    def mark_cancelled(self, ts):
        self.status = self.Status.CANCELLED
        self.cancelled_at = ts


class GoalPredicate(models.Model):
    """
    A concrete predicate attached to a Goal, implemented by a predicate Tool.
    Evaluations (on demand or later scheduled) will use `tool` with `params`.
    """

    STATUS_CHOICES = [
        ("unknown", "Unknown"),
        ("true", "True"),
        ("false", "False"),
        ("error", "Error"),
    ]

    id = models.BigAutoField(primary_key=True)

    world = models.ForeignKey("worlds.World", on_delete=models.CASCADE, related_name="predicates")
    goal = models.ForeignKey("goals.Goal", on_delete=models.CASCADE, related_name="predicates")

    # Which predicate tool implements this check
    tool = models.ForeignKey("tools.Tool", on_delete=models.PROTECT, related_name="goal_predicates")

    # Caller-chosen key to identify the predicate within the goal (unique per goal)
    key = models.CharField(max_length=128)

    # Parameters to pass to the predicate tool when evaluated
    params = models.JSONField(default=dict, blank=True)

    # Latest evaluation outcome (no re-eval scheduler yet; we’ll update this when we run it)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="unknown")
    last_payload = models.JSONField(default=dict, blank=True)  # optional: extra data returned by the predicate tool
    last_error = models.TextField(blank=True, default="")
    last_evaluated_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("goal", "key")]
        indexes = [
            models.Index(fields=["world", "goal"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:
        return f"{self.goal_id}:{self.key}"
