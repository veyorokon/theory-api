"""World authorization policies."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.agents.models import Agent
    from apps.tools.models import Tool
    from apps.worlds.models import World, WorldAgent, WorldTool


def can_agent_invoke_tool(world: World, agent: Agent, tool_ref: str) -> tuple[bool, str]:
    """
    Authorization check for tool invocation.

    Rules:
    1. WorldTool must exist and be enabled for this world
    2. Agent must be a member of the world (WorldAgent exists)
    3. Owners have implicit access to all world tools
    4. Non-owners must have AgentTool permission for this specific WorldTool

    Returns:
        (allowed, reason) tuple
    """
    from apps.agents.models import AgentTool
    from apps.worlds.models import WorldAgent, WorldTool

    # Check WorldTool exists and enabled
    try:
        world_tool = world.tools.get(tool__ref=tool_ref, enabled=True)
    except WorldTool.DoesNotExist:
        return False, "Tool not enabled in this world"

    # Check agent is in world
    try:
        world_agent = world.memberships.get(agent=agent)
    except WorldAgent.DoesNotExist:
        return False, "Agent not in world"

    # Owners bypass AgentTool checks
    if world_agent.role == WorldAgent.ROLE_OWNER:
        return True, "Owner access"

    # Check AgentTool permission for this WorldTool
    try:
        agent_tool = agent.tool_permissions.get(world_tool=world_tool, enabled=True)
        return True, "Authorized"
    except AgentTool.DoesNotExist:
        return False, "Agent not authorized for this tool"
