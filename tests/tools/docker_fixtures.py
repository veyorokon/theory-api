"""Reusable Docker container fixtures for contract tests."""

import asyncio
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

import pytest
import requests


@pytest.fixture(scope="module")
def processor_container(request):
    """
    Start processor container for tests (module-scoped for performance).

    Returns dict with:
        - ws_url: WebSocket URL (ws://localhost:<port>)
        - http_url: HTTP URL (http://localhost:<port>)
        - artifacts_dir: Host path to artifacts
        - container_id: Docker container ID

    Note: Module-scoped to share expensive container startup (~10-30s) across tests.
    Each module gets a unique port to avoid conflicts when running in parallel.
    """
    from tests.tools.subprocess_helper import run_manage_py
    import socket
    import hashlib

    # Generate unique port from module name (8000-8999 range)
    module_name = request.module.__name__
    port_hash = int(hashlib.md5(module_name.encode()).hexdigest()[:4], 16)
    host_port = 8000 + (port_hash % 1000)

    # Generate unique container name from module name + timestamp
    container_name = f"test-{module_name.replace('.', '-').replace('_', '-')}-{int(time.time() * 1000)}"

    # Build processor image
    result = run_manage_py(
        "build_processor",
        "--ref",
        "llm/litellm@1",
        "--json",
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )

    if result.returncode != 0:
        pytest.skip(f"Failed to build processor: {result.stderr}")

    build_info = json.loads(result.stdout)
    image_tag = build_info["image_tag"]

    # Check MinIO is running
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(("localhost", 9000))
        sock.close()
        if result != 0:
            pytest.skip("MinIO not running on localhost:9000. Start with: docker compose --profile full up -d minio")
    except Exception as e:
        pytest.skip(f"Cannot check MinIO availability: {e}")

    # Create temp artifacts directory
    tmp_dir = tempfile.mkdtemp(prefix="test-contract-artifacts-")
    artifacts_dir = Path(tmp_dir) / "artifacts"
    artifacts_dir.mkdir(parents=True)

    # Start container with MinIO storage configuration on unique port
    container_result = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            container_name,
            "-p",
            f"{host_port}:8000",
            "-v",
            f"{artifacts_dir}:/artifacts:rw",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--add-host",
            "minio.local:host-gateway",
            "-e",
            "IMAGE_DIGEST=sha256:test-contract-digest",
            "-e",
            "DJANGO_SETTINGS_MODULE=backend.settings.development",
            "-e",
            "STORAGE_BACKEND=minio",
            "-e",
            "ARTIFACTS_BUCKET=media",
            "-e",
            "MINIO_STORAGE_ENDPOINT=minio.local:9000",
            "-e",
            "MINIO_STORAGE_ACCESS_KEY=minioadmin",
            "-e",
            "MINIO_STORAGE_SECRET_KEY=minioadmin",
            "-e",
            "MINIO_STORAGE_USE_HTTPS=false",
            image_tag,
        ],
        capture_output=True,
        text=True,
    )

    if container_result.returncode != 0:
        pytest.skip(f"Failed to start container: {container_result.stderr}")

    container_id = container_result.stdout.strip()

    try:
        # Wait for health check on the dynamically assigned port
        for _ in range(30):
            try:
                response = requests.get(f"http://localhost:{host_port}/healthz", timeout=1)
                if response.status_code == 200:
                    break
            except requests.RequestException:
                pass
            time.sleep(1)
        else:
            # Cleanup on failure
            subprocess.run(["docker", "stop", container_id], capture_output=True)
            subprocess.run(["docker", "rm", container_id], capture_output=True)
            pytest.skip("Container failed to become ready")

        yield {
            "ws_url": f"ws://localhost:{host_port}",
            "http_url": f"http://localhost:{host_port}",
            "artifacts_dir": artifacts_dir,
            "container_id": container_id,
        }

    finally:
        # Cleanup - try graceful stop, then force kill if needed
        try:
            subprocess.run(["docker", "stop", container_id], capture_output=True, timeout=10)
        except subprocess.TimeoutExpired:
            # Force kill if graceful stop times out
            subprocess.run(["docker", "kill", container_id], capture_output=True)
        finally:
            subprocess.run(["docker", "rm", "-f", container_id], capture_output=True)


async def collect_ws_messages(
    websocket, max_messages: int = 50, timeout: float = 30.0
) -> Tuple[List[Dict[str, Any]], Dict[str, Any] | None]:
    """
    Collect WebSocket messages until RunResult.

    Args:
        websocket: WebSocket connection
        max_messages: Maximum messages to collect
        timeout: Timeout per message receive

    Returns:
        Tuple of (all_messages, final_envelope)
        final_envelope is None if no RunResult received
    """
    messages = []

    for _ in range(max_messages):
        try:
            message = await asyncio.wait_for(websocket.recv(), timeout=timeout)
            data = json.loads(message)
            messages.append(data)

            if data.get("kind") == "RunResult":
                return messages, data["content"]
        except TimeoutError:
            break

    return messages, None


@pytest.fixture(scope="module")
def reusable_orchestrator(request):
    """
    Module-scoped orchestrator with container reuse for integration tests.

    Starts one processor container per module and reuses it across all tests.
    Per twin's design:
    - Build image once per module
    - Pass reuse_container=True to orchestrator.invoke()
    - Container gets stable name + port (40000+)
    - Keep alive for entire test module
    - Cleanup on module teardown

    Returns:
        Helper function that invokes processor with reuse_container=True
    """
    from tests.tools.subprocess_helper import run_manage_py
    from apps.core.orchestrator_ws import OrchestratorWS

    # Build processor image once per module
    result = run_manage_py(
        "build_processor",
        "--ref",
        "llm/litellm@1",
        "--json",
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )

    if result.returncode != 0:
        pytest.skip(f"Failed to build processor: {result.stderr}")

    def invoke_with_reuse(ref: str, inputs: dict, **kwargs):
        """Invoke processor with container reuse enabled."""
        orch = OrchestratorWS()
        return orch.invoke(
            ref=ref,
            inputs=inputs,
            reuse_container=True,  # Key: enables container reuse
            **kwargs,
        )

    yield invoke_with_reuse

    # Cleanup: stop reused containers by label
    cleanup_result = subprocess.run(
        ["docker", "ps", "-q", "--filter", "label=com.theory.ref=llm/litellm@1"],
        capture_output=True,
        text=True,
    )

    if cleanup_result.returncode == 0 and cleanup_result.stdout.strip():
        container_ids = cleanup_result.stdout.strip().split("\n")
        for cid in container_ids:
            subprocess.run(["docker", "rm", "-f", cid], capture_output=True)
