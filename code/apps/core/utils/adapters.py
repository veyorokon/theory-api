"""Shared utilities for adapters and orchestrators."""

from __future__ import annotations
import os
import subprocess
from pathlib import Path
from typing import Dict, Any


def _normalize_digest(ref_or_digest: str | None) -> str | None:
    """
    Return `sha256:...` if input is either `sha256:...` or `something@sha256:...`.
    Otherwise, None.
    """
    if not ref_or_digest:
        return None
    s = ref_or_digest.strip()
    if "@sha256:" in s:
        return "sha256:" + s.split("@sha256:", 1)[1]
    if s.startswith("sha256:"):
        return s
    return None


def _docker_image_id(image_ref: str) -> str:
    """Get Docker image ID (sha256:...) or 'unknown'"""
    try:
        out = subprocess.check_output(
            ["docker", "inspect", "--format", "{{.Id}}", image_ref], stderr=subprocess.STDOUT, text=True
        ).strip()
        return out if out.startswith("sha256:") else "unknown"
    except Exception:
        return "unknown"


def _detect_arch() -> str:
    """Normalize architecture to {'amd64','arm64'}."""
    machine = os.uname().machine
    if machine == "x86_64":
        return "amd64"
    if machine in ("arm64", "aarch64"):
        return "arm64"
    return machine


def _get_newest_build_tag(ref: str) -> str:
    """Find the newest timestamped build tag for theory-local/{ns}-{name}-{ver}:build-*"""
    ns, rest = ref.split("/", 1)
    name, ver = rest.split("@", 1)
    repo = f"theory-local/{ns}-{name}-{ver}"

    try:
        out = subprocess.check_output(
            ["docker", "image", "ls", "--format", "{{.Repository}}:{{.Tag}}|{{.CreatedAt}}", repo],
            stderr=subprocess.STDOUT,
            text=True,
        )
    except Exception:
        raise ValueError(f"No local build images found. Run: make build-tool REF={ref}")

    candidates = []
    for line in out.splitlines():
        try:
            tag_part, created = line.split("|", 1)
        except ValueError:
            continue

        if not tag_part.endswith(":build-latest") and ":build-" in tag_part:
            # Extract the timestamp from the tag name (build-YYYYMMDDHHMMSS)
            tag_timestamp = tag_part.split(":build-")[-1]
            candidates.append((tag_part, tag_timestamp))

    if not candidates:
        raise ValueError(f"No timestamped build tags found for {repo}")

    # Sort by the timestamp in the tag name (newest first)
    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[0][0]


def _load_registry_for_ref(ref: str) -> Dict[str, Any]:
    """Load registry.yaml for a tool ref - compatibility wrapper."""
    from apps.core.registry.loader import load_processor_spec

    return load_processor_spec(ref)


def _registry_path(ref: str) -> Path:
    """Get registry.yaml path for a tool ref."""
    from apps.core.registry.loader import _registry_yaml_path_for_ref

    return _registry_yaml_path_for_ref(ref)


def _get_modal_web_url(app_name: str, function_name: str = "fastapi_app") -> str:
    """Get Modal deployment web URL for a deployed app and function."""
    try:
        import modal  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError(f"Modal SDK import failed: {e}") from e

    try:
        # Use Function.from_name to access deployed function directly
        fn = modal.Function.from_name(app_name, function_name)
        # Use get_web_url() method (web_url property is deprecated)
        url = fn.get_web_url() if hasattr(fn, "get_web_url") else fn.web_url  # type: ignore[attr-defined]
    except Exception as e:
        raise RuntimeError(f"Modal function lookup failed for {app_name}:{function_name}: {e}") from e

    if not url:
        raise RuntimeError(f"Modal function has no web_url: {app_name}:{function_name}")

    return url
