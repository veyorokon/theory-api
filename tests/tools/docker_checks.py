"""Docker availability and image existence checks for tests."""

import shutil
import subprocess
from typing import Optional


def docker_available() -> bool:
    """Check if docker command is available."""
    return shutil.which("docker") is not None


def image_exists(ref: str) -> bool:
    """Check if Docker image exists locally."""
    if not docker_available():
        return False

    try:
        result = subprocess.run(
            ["docker", "image", "inspect", ref], capture_output=True, text=True, check=False, timeout=10
        )
        return result.returncode == 0
    except Exception:
        return False


def get_image_tag_or_skip(ref: str) -> str:
    """Get image tag or raise pytest.skip if not available."""
    import pytest

    if not docker_available():
        pytest.skip("Docker not available")

    if not image_exists(ref):
        pytest.skip(f"Docker image {ref} not available locally")

    return ref
