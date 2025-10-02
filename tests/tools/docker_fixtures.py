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
def processor_container():
    """
    Start processor container for tests (module-scoped for performance).

    Returns dict with:
        - ws_url: WebSocket URL (ws://localhost:8000)
        - http_url: HTTP URL (http://localhost:8000)
        - artifacts_dir: Host path to artifacts
        - container_id: Docker container ID

    Note: Module-scoped to share expensive container startup (~10-30s) across tests.
    """
    from tests.tools.subprocess_helper import run_manage_py

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
    import socket

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

    # Start container with MinIO storage configuration
    container_result = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            f"test-contract-processor-{int(time.time())}",
            "-p",
            "8000:8000",
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
        # Wait for health check
        for _ in range(30):
            try:
                response = requests.get("http://localhost:8000/healthz", timeout=1)
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
            "ws_url": "ws://localhost:8000",
            "http_url": "http://localhost:8000",
            "artifacts_dir": artifacts_dir,
            "container_id": container_id,
        }

    finally:
        # Cleanup
        subprocess.run(["docker", "stop", container_id], capture_output=True, timeout=10)
        subprocess.run(["docker", "rm", container_id], capture_output=True)


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
