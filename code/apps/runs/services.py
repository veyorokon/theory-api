"""RunService - single entrypoint for tool invocation."""

from apps.runs.models import Run
from apps.worlds.models import World
from apps.agents.models import Agent


class RunService:
    """Orchestrates tool invocation: auth, create Run, invoke adapter, finalize."""

    @staticmethod
    def invoke_tool(
        world: World,
        agent: Agent,
        tool_ref: str,
        inputs: dict,
        adapter: str,
        mode: str,
        *,
        run_id: str | None = None,
    ) -> Run:
        """
        Invoke a tool and return the finalized Run.

        Args:
            world: World context
            agent: Agent invoking the tool
            tool_ref: Tool reference (e.g., "llm/litellm@1")
            inputs: Input payload for the tool
            adapter: Adapter to use ("local" or "modal")
            mode: Execution mode ("mock" or "real")
            run_id: Optional explicit run ID (default: auto-generated)

        Returns:
            Run instance (finalized with outputs)
        """
        import uuid

        # Generate run ID
        if not run_id:
            run_id = str(uuid.uuid4())

        # Create Run with world-scoped path (world_id is security boundary)
        write_prefix = f"/{world.id}/{run_id}/"
        run = Run.objects.create(
            id=run_id,
            world=world,
            caller_agent=agent,
            ref=tool_ref,
            mode=mode,
            adapter=adapter,
            status=Run.Status.PENDING,
            write_prefix=write_prefix,
            inputs=inputs,
        )

        # Get adapter and invoke
        from apps.core.utils.adapters import get_adapter_for_run

        adapter_impl = get_adapter_for_run(adapter)

        try:
            # Adapter handles full invocation and returns envelope
            envelope = adapter_impl.invoke_run(run)
            run.finalize(envelope)
        except Exception as e:
            # Mark run as failed
            run.status = Run.Status.FAILED
            run.error_message = str(e)
            run.save()
            raise

        return run
