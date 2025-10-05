# apps/worlds/models.py
from __future__ import annotations
import uuid
from django.conf import settings
from django.db import models
from django.utils.text import slugify

User = settings.AUTH_USER_MODEL


class World(models.Model):
    """
    The shared state boundary for humans + agents.
    Everything (goals, plans, runs, artifacts) is scoped to a World.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Human-friendly ID you can put in paths/URLs and S3 prefixes
    key = models.SlugField(max_length=64, unique=True, help_text="Stable slug. e.g. 'acme-campaign-q4'")

    # Optional display fields
    title = models.CharField(max_length=200, blank=True, default="")
    description = models.TextField(blank=True, default="")

    # Ownership / tenancy
    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="worlds_created"
    )

    # Free-form small config for the world (safe defaults only)
    settings_json = models.JSONField(blank=True, null=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "world"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return self.key

    @property
    def artifacts_prefix(self) -> str:
        """
        Canonical root prefix for this world's artifacts in S3/MinIO.
        Use this to build write_prefixes for runs:
          f"{self.artifacts_prefix}outputs/{ref_slug}/{run_id}/"
        """
        # Keep the global ARTIFACTS_PREFIX (e.g. "artifacts/") from settings
        base = getattr(settings, "ARTIFACTS_PREFIX", "artifacts/")
        if not base.endswith("/"):
            base += "/"
        return f"/{base}worlds/{self.key}/"  # note leading "/" to match current convention

    def save(self, *args, **kwargs):
        # help if someone passes a title but no key
        if not self.key and self.title:
            self.key = slugify(self.title)[:64] or str(uuid.uuid4())[:12]
        super().save(*args, **kwargs)


class WorldAgent(models.Model):
    """
    Agent membership in a World (RBAC + per-world limits).
    Replaces WorldMember - agents can be human or autonomous.
    """

    ROLE_OWNER = "owner"
    ROLE_EDITOR = "editor"
    ROLE_VIEWER = "viewer"
    ROLE_CHOICES = [(ROLE_OWNER, "Owner"), (ROLE_EDITOR, "Editor"), (ROLE_VIEWER, "Viewer")]

    world = models.ForeignKey(World, on_delete=models.CASCADE, related_name="memberships")
    agent = models.ForeignKey("agents.Agent", on_delete=models.CASCADE, related_name="world_memberships")
    role = models.CharField(max_length=16, choices=ROLE_CHOICES, default=ROLE_EDITOR)

    # World-scoped overrides (nullable = inherit from Agent)
    budget_micro_override = models.BigIntegerField(null=True, blank=True)
    concurrency_override = models.PositiveIntegerField(null=True, blank=True)

    # Additional prefs
    prefs = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "world_agent"
        unique_together = (("world", "agent"),)
        indexes = [models.Index(fields=["world", "role"])]

    def __str__(self) -> str:
        return f"{self.agent} @ {self.world} ({self.role})"

    def effective_budget_micro(self) -> int:
        """World override > Agent default > settings default."""
        return self.budget_micro_override or self.agent.effective_budget_micro()

    def effective_concurrency(self) -> int:
        """World override > Agent default > settings default."""
        return self.concurrency_override or self.agent.effective_concurrency()
