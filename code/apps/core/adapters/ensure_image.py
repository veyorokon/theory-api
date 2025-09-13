"""
Shared image resolution for local and modal adapters.

Provides unified image handling with build support.
"""

import subprocess
from typing import Dict, Any


def ensure_image(proc_spec: Dict[str, Any], build: bool = False) -> str:
    """
    Ensure container image is available and return digest.

    Args:
        proc_spec: Processor specification from registry
        build: Whether to build if no OCI digest available

    Returns:
        Image reference (repo@sha256:... or repo:tag)

    Raises:
        ValueError: If no image available and build not permitted
        RuntimeError: If build or pull operation fails
    """
    image_spec = proc_spec.get("image", {})
    build_spec = proc_spec.get("build", {})

    # First preference: use existing OCI digest
    if "oci" in image_spec:
        oci_ref = image_spec["oci"]
        _ensure_image_pulled(oci_ref)
        return oci_ref

    # Second preference: build if requested and build spec exists
    if build and build_spec:
        return _build_image(build_spec)

    # No image available
    if build_spec:
        raise ValueError(f"No image.oci specified and --build not enabled. Use --build to build from {build_spec}")
    else:
        raise ValueError("No image.oci specified and no build configuration available")


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

        # Pull image
        subprocess.run(["docker", "pull", image_ref], capture_output=True, text=True, check=True)

    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to pull image {image_ref}: {e.stderr}")
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
