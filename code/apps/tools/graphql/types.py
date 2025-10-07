"""GraphQL types for tools."""

from __future__ import annotations

import strawberry
from strawberry import auto

from apps.tools import models


@strawberry.django.type(models.Tool)
class ToolType:
    """Tool GraphQL type."""

    ref: auto
    namespace: auto
    name: auto
    version: auto
    ref_slug: auto
    kind: auto
    enabled: auto
