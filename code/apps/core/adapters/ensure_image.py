"""
Shared image resolution for local and modal adapters.

Provides unified image handling with build support.
"""

from __future__ import annotations
import os
import re
import subprocess
from typing import Any, Dict

# Regex to validate SHA256 digest format
_DIGEST_RE = re.compile(r"@sha256:[0-9a-fA-F]{64}$")


def is_valid_sha256_digest(ref: str) -> bool:
    """Check if image reference has a valid SHA256 digest."""
    return bool(ref and _DIGEST_RE.search(ref))


def _is_pinned(ref: str | None) -> bool:
    """Check if image reference has a valid SHA256 digest."""
    return is_valid_sha256_digest(ref or "")


def ensure_image(proc_spec: Dict[str, Any], *, adapter: str, build: bool = False, force_build: bool = False) -> str:
    """
    Return an image reference to run.

    Rules:
      - adapter == "modal" (or any remote runtime): must use pinned digest. We never build here.
      - adapter == "local":
          * if force_build and build_spec: build and return local tag
          * elif build and build_spec: build and return local tag
          * elif image.oci present: pull and return digest
          * else: error

    Args:
        proc_spec: Processor specification from registry
        adapter: Adapter type ("local", "modal", etc.)
        build: Whether to build from source for local adapter
        force_build: Force build even if OCI is present (local adapter only)

    Returns:
        Image reference (digest for remote, tag or digest for local)

    Raises:
        RuntimeError: If requirements cannot be satisfied
    """
    image_spec = proc_spec.get("image", {}) or {}
    build_spec = proc_spec.get("build", {}) or {}

    if adapter != "local":
        # Remote runtimes are digest-only for determinism.
        oci = image_spec.get("oci")
        if not oci or not _is_pinned(oci):
            raise RuntimeError("Remote adapters require a pinned image digest (image.oci).")
        _ensure_image_pulled(oci)
        return oci

    # Local adapter - follow Twin's specified order
    oci = image_spec.get("oci")

    # 1. If force_build and build_spec: build
    if force_build and build_spec or build and build_spec:
        return _build_local_image(build_spec)

    # 3. Elif oci and is_valid_sha256_digest(oci): pull
    elif oci and is_valid_sha256_digest(oci):
        _ensure_image_pulled(oci)
        return oci

    # 4. Else: raise with clear message
    else:
        from apps.core.errors import ERR_IMAGE_UNPINNED

        if oci and not is_valid_sha256_digest(oci):
            raise RuntimeError(f"{ERR_IMAGE_UNPINNED}: Invalid or pending digest: {oci}")
        else:
            raise RuntimeError(f"{ERR_IMAGE_UNPINNED}: No usable image reference and no build spec")


def _ensure_image_pulled(image_ref: str) -> None:
    """
    Ensure image is pulled locally.

    Args:
        image_ref: Image reference to pull

    Raises:
        RuntimeError: If pull operation fails
    """
    try:
        # Check if image exists locally
        result = subprocess.run(["docker", "image", "inspect", image_ref], capture_output=True, text=True, check=False)

        if result.returncode == 0:
            # Image exists locally
            return

        # Optional explicit platform for CI/codespaces
        platform = os.getenv("DOCKER_PULL_PLATFORM")  # e.g., "linux/amd64"
        if platform:
            subprocess.run(
                ["docker", "pull", "--platform", platform, image_ref], capture_output=True, text=True, check=True
            )
        else:
            subprocess.run(["docker", "pull", image_ref], capture_output=True, text=True, check=True)

    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to pull image {image_ref}: {e.stderr}")
    except FileNotFoundError:
        raise RuntimeError("Docker not found. Please install Docker.")


def _build_local_image(build_spec: Dict[str, Any], tag: str | None = None) -> str:
    """
    Build a local image for the *local adapter* only.
    Returns a tag suitable for `docker run` (not a digest).
    """
    from django.conf import settings
    from pathlib import Path

    context = build_spec.get("context", ".")
    dockerfile = build_spec.get("dockerfile", "Dockerfile")
    tag = tag or build_spec.get("tag") or "theory-local-build:dev"

    # Make context path absolute from BASE_DIR
    if not Path(context).is_absolute():
        context_path = Path(settings.BASE_DIR) / context
    else:
        context_path = Path(context)

    dockerfile_path = context_path / dockerfile
    platform = os.getenv("DOCKER_BUILD_PLATFORM")  # optional (e.g., "linux/amd64")

    if platform:
        cmd = [
            "docker",
            "buildx",
            "build",
            "--platform",
            platform,
            "-f",
            str(dockerfile_path),
            "-t",
            tag,
            "--load",
            str(context_path),
        ]
    else:
        cmd = ["docker", "build", "-f", str(dockerfile_path), "-t", tag, str(context_path)]

    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        return tag
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to build local image: {e.stderr}")
    except FileNotFoundError:
        raise RuntimeError("Docker not found. Please install Docker.")


def _build_image(build_spec: Dict[str, Any]) -> str:
    """
    Build image from build specification and return digest.

    Args:
        build_spec: Build configuration from registry

    Returns:
        Built image digest (sha256:...)

    Raises:
        RuntimeError: If build operation fails
    """
    from django.conf import settings
    from pathlib import Path

    context = build_spec.get("context", ".")
    dockerfile = build_spec.get("dockerfile", "Dockerfile")

    # Make context path absolute from BASE_DIR
    if not Path(context).is_absolute():
        context_path = Path(settings.BASE_DIR) / context
    else:
        context_path = Path(context)

    # Generate build tag
    import hashlib
    import json

    build_hash = hashlib.sha256(json.dumps(build_spec, sort_keys=True).encode()).hexdigest()[:12]
    image_tag = f"theory-local-build:{build_hash}"

    try:
        # Build image using buildx for consistent digest
        dockerfile_path = context_path / dockerfile
        build_cmd = [
            "docker",
            "buildx",
            "build",
            "-t",
            image_tag,
            "-f",
            str(dockerfile_path),
            "--load",
            str(context_path),
        ]

        build_result = subprocess.run(build_cmd, capture_output=True, text=True, check=True)

        # Get the image digest
        inspect_cmd = ["docker", "inspect", "--format={{.Id}}", image_tag]

        inspect_result = subprocess.run(inspect_cmd, capture_output=True, text=True, check=True)

        # Return the digest (already in sha256:... format)
        digest = inspect_result.stdout.strip()
        return digest

    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to build image: {e.stderr}")
    except FileNotFoundError:
        raise RuntimeError("Docker not found. Please install Docker.")


def ensure_image_pinned(adapter: str, spec: Dict[str, Any], build: bool = False) -> Dict[str, Any]:
    """
    Policy:
      - modal: requires pinned digest (oci contains '@sha256:')
      - local/mock: allows unpinned (development flexibility)
      - others: require pinned by default
    Returns canonical success/error envelope (no exceptions).
    """
    oci = ((spec or {}).get("image") or {}).get("oci", "") or ""
    pinned = "@sha256:" in oci

    # Validate SHA256 format if present
    if pinned:
        digest_part = oci.split("@sha256:")[-1]
        if len(digest_part) != 64 or not all(c in "0123456789abcdef" for c in digest_part.lower()):
            return {
                "success": False,
                "error": {"code": "ERR_IMAGE_UNPINNED", "message": "Invalid SHA256 digest format"},
            }

    if adapter == "modal" and not pinned:
        return {
            "success": False,
            "error": {"code": "ERR_IMAGE_UNPINNED", "message": "Modal adapter requires pinned digest"},
        }

    # Local and mock adapters allow unpinned for development flexibility
    if adapter in ("local", "mock"):
        return {"success": True, "image_ref": oci}

    if not pinned:
        return {"success": False, "error": {"code": "ERR_IMAGE_UNPINNED", "message": "Unpinned image not allowed"}}

    return {"success": True, "image_ref": oci}
