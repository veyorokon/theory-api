"""
Integration test fixtures.

Manages tool container lifecycle and provides adapter interface.
"""

import os
import pytest


def pytest_generate_tests(metafunc):
    """Dynamically parametrize tests with enabled tool refs from DB."""
    if "tool_ref" in metafunc.fixturenames:
        import pytest_django.plugin

        # Access blocker via config.stash (pytest 8.x pattern)
        blocker = metafunc.config.stash[pytest_django.plugin.blocking_manager_key]

        from apps.tools.models import Tool

        with blocker.unblock():
            enabled_refs = list(Tool.objects.filter(enabled=True).values_list("ref", flat=True))

        if not enabled_refs:
            pytest.skip("No enabled tools found")

        metafunc.parametrize("tool_ref", enabled_refs)


# ============================================================================
# Tool lifecycle (session-scoped)
# ============================================================================
@pytest.fixture(scope="session", autouse=True)
def prepare_tools(adapter_type, django_db_setup, django_db_blocker):
    """
    Prepare all enabled tools before integration tests run.

    For local adapter:
    - Builds images (if needed)
    - Starts containers
    - Stops containers on teardown

    For modal adapter:
    - Assumes deployments already exist (handled by Makefile/CI)
    - No container management needed
    """
    if adapter_type != "local":
        # Modal adapter: deployments managed externally
        yield
        return

    # Local adapter: manage containers
    from django.core.management import call_command
    from apps.tools.models import Tool

    # Get all enabled tools (need blocker for session-scoped fixture)
    with django_db_blocker.unblock():
        enabled_refs = list(Tool.objects.filter(enabled=True).values_list("ref", flat=True))

    if not enabled_refs:
        pytest.skip("No enabled tools found")

    platform = os.getenv("PLATFORM", "amd64")

    # Build and start each tool
    for ref in enabled_refs:
        try:
            import time
            import requests
            import json
            from io import StringIO

            # Build image
            call_command("imagectl", "build", "--ref", ref, "--platform", platform)
            # Start container
            call_command("localctl", "start", "--ref", ref, "--platform", platform)

            # Get URL from localctl
            url_output = StringIO()
            call_command("localctl", "url", "--ref", ref, stdout=url_output)
            url_data = json.loads(url_output.getvalue().strip())
            base_url = url_data["url"]

            # Wait for container to be healthy
            health_url = f"{base_url}/healthz"
            for _attempt in range(30):  # 30 attempts, 1s each = 30s max
                try:
                    resp = requests.get(health_url, timeout=1)
                    if resp.status_code == 200:
                        break
                except Exception:
                    pass
                time.sleep(1)
            else:
                raise RuntimeError(f"Container {ref} failed health check after 30s")

        except Exception as e:
            pytest.fail(f"Failed to prepare tool {ref}: {e}")

    yield  # Run all tests

    # Cleanup: stop all containers
    try:
        call_command("localctl", "stop", "--all")
    except Exception:
        pass  # Best effort cleanup


# ============================================================================
# Adapter interface for tests
# ============================================================================
@pytest.fixture
def adapter(adapter_type):
    """
    Provide adapter interface for invoking tools.

    Usage in tests:
        result = adapter.invoke(
            ref="llm/litellm@1",
            mode="mock",
            inputs={...},
            artifact_scope="local",
        )
    """
    from apps.core.tool_runner import ToolRunner

    runner = ToolRunner()

    class TestAdapter:
        def invoke(self, ref, mode, inputs, artifact_scope, run_id=None):
            """
            Invoke tool and return final envelope.

            Args:
                ref: Tool reference (e.g., "llm/litellm@1")
                mode: "mock" or "real"
                inputs: Input dict (e.g., {"schema": "v1", "params": {...}})
                artifact_scope: "world" or "local"
                run_id: Optional explicit run ID

            Returns:
                dict: Final envelope
            """
            return runner.invoke(
                ref=ref,
                mode=mode,
                inputs=inputs,
                stream=False,
                artifact_scope=artifact_scope,
                adapter=adapter_type,
                run_id=run_id,
            )

        def invoke_stream(self, ref, mode, inputs, artifact_scope, run_id=None):
            """
            Invoke tool and return event stream iterator.

            Yields:
                dict: Events (Token, Event, Log) and final envelope
            """
            return runner.invoke(
                ref=ref,
                mode=mode,
                inputs=inputs,
                stream=True,
                artifact_scope=artifact_scope,
                adapter=adapter_type,
                run_id=run_id,
            )

    return TestAdapter()


@pytest.fixture
def enabled_tool_refs(django_db_blocker):
    """
    Get list of all enabled tool refs from database.

    Returns:
        list[str]: Tool refs (e.g., ["llm/litellm@1"])
    """
    from apps.tools.models import Tool

    with django_db_blocker.unblock():
        return list(Tool.objects.filter(enabled=True).values_list("ref", flat=True))
