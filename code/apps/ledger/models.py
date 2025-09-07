from django.db import models

from apps.plans.models import Plan


class Event(models.Model):
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE)
    seq = models.PositiveBigIntegerField()
    prev_hash = models.CharField(max_length=128, null=True, blank=True)
    this_hash = models.CharField(max_length=128)
    payload = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['plan', 'seq'], 
                name='uq_event_plan_seq'
            )
        ]

    def __str__(self):
        return f"{self.plan.key}.{self.seq} ({self.payload.get('event_type', 'unknown')})"
