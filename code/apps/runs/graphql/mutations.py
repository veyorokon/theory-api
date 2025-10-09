"""GraphQL mutations for runs."""

from __future__ import annotations

import uuid
import strawberry
from strawberry.types import Info
from typing import Optional

from apps.runs.graphql.types import RunType
from apps.runs.services import RunService
from apps.runs.models import RunArtifact
from apps.worlds.models import World
from apps.agents.models import Agent
from apps.artifacts.services import ArtifactService


@strawberry.input
class CreateRunInput:
    """
    Input for creating a run.

    inputData: Inline data to write as artifacts (convenience)
    inputReferences: References to existing artifacts (world:// URIs)

    Django will merge both into final inputs dict with world:// URIs.
    """

    world_id: str
    agent_id: str
    tool_ref: str
    input_data: strawberry.scalars.JSON | None = None  # Inline data
    input_references: strawberry.scalars.JSON | None = None  # world:// URIs
    adapter: str = "local"
    mode: str = "mock"


@strawberry.type
class RunMutation:
    """Run mutations."""

    @strawberry.mutation
    def create_run(self, input: CreateRunInput, info: Info) -> RunType:
        """
        Create and execute a run.

        Flow:
        1. Write inline inputData as artifacts
        2. Merge with inputReferences
        3. Create Run with world:// URIs
        4. Invoke tool (adapter hydrates URIs)
        """
        # Validate world exists
        try:
            world = World.objects.get(id=input.world_id)
        except World.DoesNotExist:
            raise ValueError(f"World {input.world_id} not found")

        # Validate agent exists
        try:
            agent = Agent.objects.get(id=input.agent_id)
        except Agent.DoesNotExist:
            raise ValueError(f"Agent {input.agent_id} not found")

        # Generate run ID early so we can write artifacts to its path
        run_id = str(uuid.uuid4())

        # Build final inputs dict
        final_inputs = {}

        # Write inline data as artifacts
        if input.input_data:
            for key, value in input.input_data.items():
                artifact = ArtifactService.create_inline_artifact(world=world, run_id=run_id, key=key, value=value)
                final_inputs[key] = artifact.uri

        # Merge with references (references override inline if conflict)
        if input.input_references:
            final_inputs.update(input.input_references)

        # Invoke tool via RunService
        run = RunService.invoke_tool(
            world=world,
            agent=agent,
            tool_ref=input.tool_ref,
            inputs=final_inputs,
            adapter=input.adapter,
            mode=input.mode,
            run_id=run_id,
        )

        # Create RunArtifact links for inputs
        for key, uri in final_inputs.items():
            # Find artifact by URI
            try:
                artifact = world.artifacts.get(uri=uri)
                RunArtifact.objects.create(
                    run=run,
                    artifact=artifact,
                    direction=RunArtifact.DIRECTION_IN,
                    key=key,
                )
            except Exception:
                # Skip if artifact not found (may be external reference)
                pass

        return run
