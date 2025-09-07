from django.db import models


class Plan(models.Model):
    key = models.CharField(max_length=128, unique=True)
    reserved_micro = models.BigIntegerField(default=0)
    spent_micro = models.BigIntegerField(default=0)

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
