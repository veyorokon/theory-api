"""GraphQL schema root."""

from __future__ import annotations

import strawberry

from apps.tools.graphql.queries import ToolQuery


@strawberry.type
class Query(ToolQuery):
    """Root Query - combines all app queries."""

    pass


schema = strawberry.Schema(query=Query)
