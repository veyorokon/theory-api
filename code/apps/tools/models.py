# apps/tools/models.py
from __future__ import annotations
from django.db import models

# ------------------------------------------------------------
# Tool catalog (what exists), and WorldTool (what a World can use)
# ------------------------------------------------------------


class Tool(models.Model):
    """
    Catalog entry for a runnable unit (container-first “processor”) or a predicate tool.
    One row per (namespace/name@version). Keep it small; the *runtime* spec lives in registry.yaml
    but we denormalize key bits here for discovery/filtering.
    """

    KIND_CHOICES = [
        ("processor", "Processor"),  # produces artifacts / side-effects
        ("predicate", "Predicate"),  # returns boolean truth with optional payload
    ]

    id = models.BigAutoField(primary_key=True)

    # Identity
    namespace = models.CharField(max_length=64)
    name = models.CharField(max_length=64)
    version = models.PositiveIntegerField()
    # e.g., "ns/name@1"
    ref = models.CharField(max_length=160, unique=True)
    # slug used for storage paths: ns_name
    ref_slug = models.CharField(max_length=160, db_index=True)

    kind = models.CharField(max_length=16, choices=KIND_CHOICES, default="processor")
    enabled = models.BooleanField(default=True)

    # Denormalized snapshots from registry.yaml (optional but useful)
    inputs_schema = models.JSONField(default=dict, blank=True)
    outputs_decl = models.JSONField(default=list, blank=True)  # [{"path": "...", "mime": "..."}]
    required_secrets = models.JSONField(default=list, blank=True)  # ["OPENAI_API_KEY", ...]

    # Where registry.yaml lives on disk (server-side) so ops can find/update it
    registry_path = models.CharField(max_length=512, blank=True, default="")

    # OCI digests by platform (if pinned)
    digest_amd64 = models.CharField(max_length=128, blank=True, default="")
    digest_arm64 = models.CharField(max_length=128, blank=True, default="")

    # Runtime configuration from registry
    timeout_s = models.PositiveIntegerField(default=600)
    cpu = models.CharField(max_length=8, blank=True, default="1")
    memory_gb = models.PositiveIntegerField(default=2)
    gpu = models.CharField(max_length=32, blank=True, default="")  # e.g., "A10G", "T4", or empty

    class Meta:
        unique_together = [("namespace", "name", "version")]
        indexes = [
            models.Index(fields=["ref_slug"]),
            models.Index(fields=["kind", "enabled"]),
        ]

    def __str__(self) -> str:
        return self.ref


class WorldTool(models.Model):
    """
    Grants a World access to a Tool. Lets us scope capabilities per world, and
    hang per-world config (overrides, quotas) without duplicating Tool rows.
    """

    id = models.BigAutoField(primary_key=True)

    world = models.ForeignKey("worlds.World", on_delete=models.CASCADE, related_name="world_tools")
    tool = models.ForeignKey("tools.Tool", on_delete=models.CASCADE, related_name="world_bindings")

    # Optional per-world overrides
    config = models.JSONField(default=dict, blank=True)  # e.g., tuned defaults for params
    quota_micro = models.BigIntegerField(null=True, blank=True)  # optional per-world budget cap for this tool

    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("world", "tool")]
        indexes = [
            models.Index(fields=["world", "enabled"]),
        ]

    def __str__(self) -> str:
        return f"{self.world_id}:{self.tool.ref}"


class ToolIO(models.Model):
    """
    Unified declaration for both inputs and outputs of a Tool.
    One row per top-level field/path.

    direction = IN: a named input field a caller must supply
    direction = OUT: an artifact path the tool will write under write_prefix
    """

    DIRECTION = (("IN", "Input"), ("OUT", "Output"))

    id = models.BigAutoField(primary_key=True)
    tool = models.ForeignKey(Tool, on_delete=models.CASCADE, related_name="ios")
    direction = models.CharField(max_length=3, choices=DIRECTION)

    # For IN:
    # - key identifies the input field (e.g., "params", "image", "prompt")
    # For OUT:
    # - key is a friendly handle for wiring (e.g., "primary_text", "thumbnail")
    key = models.CharField(max_length=128)

    # Schema/typing hints (works for IN and OUT metadata)
    schema = models.JSONField(default=dict, blank=True)  # JSON Schema fragment or light spec
    description = models.CharField(max_length=512, blank=True, default="")

    # Storage-related (mostly relevant for OUT; optional for IN that accept files)
    path = models.CharField(max_length=256, blank=True, default="")  # e.g., "outputs/text/response.txt"
    mime = models.CharField(max_length=128, blank=True, default="")  # e.g., "text/plain"

    # For OUT only: indicates this output is a scalar value extracted from results.json
    # (e.g., token_count, score) rather than a standalone file artifact
    is_scalar_result = models.BooleanField(default=False)

    # Presentation / selection
    role = models.CharField(max_length=64, blank=True, default="")  # e.g., "primary", "preview"
    required = models.BooleanField(default=False)  # primarily for IN
    order = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = [("tool", "direction", "key")]
        ordering = ["tool_id", "direction", "order", "id"]

    def __str__(self) -> str:
        return f"{self.tool.ref}:{self.direction}:{self.key}"
