"""Agent models - unified identity for humans and autonomous agents."""

from __future__ import annotations

import os
import uuid

from django.conf import settings
from django.db import models

User = settings.AUTH_USER_MODEL


class Agent(models.Model):
    """Unified identity: humans and autonomous agents."""

    KIND_HUMAN = "human"
    KIND_AUTONOMOUS = "autonomous"
    KIND_CHOICES = [(KIND_HUMAN, "Human"), (KIND_AUTONOMOUS, "Autonomous")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=24, choices=KIND_CHOICES, default=KIND_HUMAN)

    # Human agents link to Django User
    user = models.OneToOneField(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="agent")

    # Unified config (persona, model prefs, program, runtime)
    config = models.JSONField(default=dict, blank=True)

    # Global agent limits (world can override via WorldAgent)
    budget_micro_cap = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="Global budget cap; null = use settings.DEFAULT_AGENT_BUDGET_MICRO",
    )
    concurrency_limit = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Global concurrency; null = use settings.DEFAULT_AGENT_CONCURRENCY",
    )

    # Spawn lineage
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "agent"
        indexes = [models.Index(fields=["kind"])]

    def __str__(self):
        return f"{self.name} ({self.kind})"

    def effective_budget_micro(self) -> int:
        """Resolve budget with fallback to settings default."""
        return self.budget_micro_cap or getattr(settings, "DEFAULT_AGENT_BUDGET_MICRO", 1_000_000)

    def effective_concurrency(self) -> int:
        """Resolve concurrency with fallback to settings default."""
        return self.concurrency_limit or getattr(settings, "DEFAULT_AGENT_CONCURRENCY", 5)


class AgentCredential(models.Model):
    """Agent credentials (API keys, tokens) stored as references."""

    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name="credentials")
    name = models.CharField(max_length=64)  # "OPENAI_API_KEY", etc.
    value_ref = models.CharField(max_length=255, help_text="Format: 'env:VAR_NAME' or 'kms:ARN' (extend as needed)")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "agent_credential"
        unique_together = (("agent", "name"),)

    def __str__(self):
        return f"{self.agent.name}:{self.name}"

    def resolve(self) -> str:
        """Resolve credential reference to actual value."""
        if self.value_ref.startswith("env:"):
            var_name = self.value_ref[4:]
            value = os.getenv(var_name)
            if not value:
                raise ValueError(f"Credential {self.name} env var {var_name} not set")
            return value
        # Add kms:, vault:, etc. handlers here
        raise ValueError(f"Unknown credential reference type: {self.value_ref}")


class AgentTool(models.Model):
    """
    Agent permission to use a WorldTool.
    FK to WorldTool (not Tool) ensures agent can only access tools in their worlds.
    """

    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name="tool_permissions")
    world_tool = models.ForeignKey("tools.WorldTool", on_delete=models.CASCADE, related_name="agent_permissions")
    enabled = models.BooleanField(default=True)

    # Agent-scoped overrides for this specific world tool
    default_inputs_override = models.JSONField(null=True, blank=True)
    budget_micro_override = models.BigIntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "agent_tool"
        unique_together = (("agent", "world_tool"),)

    def __str__(self):
        return f"{self.agent.name} → {self.world_tool}"

    def effective_budget_micro(self) -> int | None:
        """Agent override > WorldTool default > None."""
        return self.budget_micro_override or self.world_tool.budget_micro_cap
