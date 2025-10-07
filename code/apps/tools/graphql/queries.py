"""GraphQL queries for tools."""

from __future__ import annotations

from typing import List

import strawberry

from apps.tools import models
from apps.tools.graphql.types import ToolType


@strawberry.type
class ToolQuery:
    """Tool queries."""

    @strawberry.field
    def tools(self) -> List[ToolType]:
        """List all tools."""
        return models.Tool.objects.all()

    @strawberry.field
    def tool(self, ref: str) -> ToolType | None:
        """Get tool by ref."""
        try:
            return models.Tool.objects.get(ref=ref)
        except models.Tool.DoesNotExist:
            return None
