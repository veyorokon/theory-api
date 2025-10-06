"""GraphQL schema root."""

from __future__ import annotations

import strawberry

from apps.tools.graphql.queries import ToolQuery
from apps.runs.graphql.mutations import RunMutation


@strawberry.type
class Query(ToolQuery):
    """Root Query - combines all app queries."""

    pass


@strawberry.type
class Mutation(RunMutation):
    """Root Mutation - combines all app mutations."""

    pass


schema = strawberry.Schema(query=Query, mutation=Mutation)
