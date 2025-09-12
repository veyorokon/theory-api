from django.db import models
from django.db.models import Q

from apps.plans.models import Plan


class Transition(models.Model):
    STATUS_CHOICES = [
        ("pending", "pending"),
        ("runnable", "runnable"),
        ("applying", "applying"),
        ("running", "running"),
        ("succeeded", "succeeded"),
        ("failed", "failed"),
    ]

    plan = models.ForeignKey(Plan, on_delete=models.CASCADE)
    key = models.CharField(max_length=128)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="pending")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["plan", "key"], name="uq_transition_plan_key"),
            models.UniqueConstraint(
                fields=["plan"], condition=Q(status__in=["applying", "running"]), name="uq_plan_single_writer"
            ),
        ]

    def __str__(self):
        return f"{self.plan.key}.{self.key} ({self.status})"


class Execution(models.Model):
    transition = models.ForeignKey(Transition, on_delete=models.CASCADE)
    attempt_idx = models.PositiveIntegerField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["transition", "attempt_idx"], name="uq_execution_attempt")]

    def __str__(self):
        return f"{self.transition}.attempt{self.attempt_idx}"
