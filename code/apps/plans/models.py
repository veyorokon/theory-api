from django.db import models


class Project(models.Model):
    """Lightweight grouping for multiple Plans under a tenant.

    Control-plane only: execution safety remains strictly per-Plan.
    """
    key = models.CharField(max_length=128, unique=True)
    title = models.CharField(max_length=256, blank=True)
    defaults_json = models.JSONField(null=True, blank=True)

    def __str__(self):
        return self.key


class Plan(models.Model):
    key = models.CharField(max_length=128, unique=True)
    reserved_micro = models.BigIntegerField(default=0)
    spent_micro = models.BigIntegerField(default=0)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=models.Q(reserved_micro__gte=0), 
                name='plan_reserved_nonneg'
            ),
            models.CheckConstraint(
                check=models.Q(spent_micro__gte=0), 
                name='plan_spent_nonneg'
            ),
        ]

    def __str__(self):
        return self.key
