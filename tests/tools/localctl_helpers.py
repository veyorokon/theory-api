"""Helper utilities for tests that use localctl-managed containers."""

import json
import subprocess


def get_container_port(ref: str) -> int:
    """
    Get assigned port for container from localctl status.

    Assumes container already started by Makefile (via `localctl start`).

    Args:
        ref: Processor ref (e.g., "llm/litellm@1")

    Returns:
        Port number where container is listening

    Raises:
        RuntimeError: If container not running (test setup is broken)
    """
    result = subprocess.run(
        ["python", "manage.py", "localctl", "status", "--ref", ref],
        cwd="code",
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError("Container not running. Run: make test-integration")

    status = json.loads(result.stdout)
    if not status.get("containers"):
        raise RuntimeError(f"Container for {ref} not found")

    port = status["containers"][0]["port"]
    if port is None:
        raise RuntimeError(f"Container for {ref} has no port assigned")

    return port


def get_ws_url(ref: str) -> str:
    """Get WebSocket URL for processor ref."""
    port = get_container_port(ref)
    return f"ws://localhost:{port}/run"


def get_http_url(ref: str) -> str:
    """Get HTTP base URL for processor ref."""
    port = get_container_port(ref)
    return f"http://localhost:{port}"
