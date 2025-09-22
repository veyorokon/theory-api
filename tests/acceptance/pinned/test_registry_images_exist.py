# tests/acceptance/pinned/test_registry_images_exist.py
"""
Supply-chain acceptance: every pinned processor image must exist in GHCR
and advertise BOTH linux/amd64 and linux/arm64 in its manifest list.

This test is lane-safe:
- No network credentials or secrets are required (public GHCR manifest read).
- Pinned-only (no --build), purely supply-chain validation.
"""

from __future__ import annotations

import json
import subprocess
from typing import Dict, Any, Iterable

import pytest
from tests.tools.registry import each_processor_spec


REQUIRED_PLATFORMS = ("linux/amd64", "linux/arm64")


def _imagetools_inspect(ref: str) -> str:
    """
    Call `docker buildx imagetools inspect <ref>` and return stdout.
    Fail with a clean pytest assertion if the manifest is missing.
    """
    try:
        out = subprocess.check_output(
            ["docker", "buildx", "imagetools", "inspect", ref],
            stderr=subprocess.STDOUT,
            text=True,
        )
        return out
    except subprocess.CalledProcessError as e:
        raise AssertionError(
            f"Pinned image not found or unreadable: {ref}\n\ndocker buildx imagetools inspect output:\n{e.output}"
        )


def _platforms_from_text(text: str) -> Iterable[str]:
    """
    Parse platforms from imagetools text output in a tolerant way.
    We avoid strict parsing to keep this robust across Docker versions.
    """
    plats: set[str] = set()
    for line in text.splitlines():
        line = line.strip()
        # Common formats seen in imagetools output:
        # - "Name:      ghcr.io/...@sha256:..."
        # - "MediaType: application/vnd.docker.distribution.manifest.list.v2+json"
        # - "Manifests:" then platform lines like "  Name: ... Platform: linux/amd64"
        # - Or summary lines containing "linux/amd64", "linux/arm64"
        if "linux/amd64" in line:
            plats.add("linux/amd64")
        if "linux/arm64" in line:
            plats.add("linux/arm64")
    return sorted(plats)


@pytest.mark.supplychain
@pytest.mark.acceptance
def test_every_pinned_processor_image_exists_and_is_multiarch() -> None:
    """
    Iterate every processor spec discovered from the registry and assert
    its pinned OCI reference exists and includes both required platforms.
    """
    failures: list[str] = []

    for spec in each_processor_spec():  # yields {"ref": "...", "image": {"oci": "ghcr.io/...@sha256:..."} , ...}
        ref = spec.get("ref") or "<unknown-ref>"
        oci = (spec.get("image") or {}).get("oci")
        if not oci or "@sha256:" not in oci:
            failures.append(f"[{ref}] missing or unpinned image.oci: {oci!r}")
            continue

        out = _imagetools_inspect(oci)
        platforms = set(_platforms_from_text(out))
        missing = [p for p in REQUIRED_PLATFORMS if p not in platforms]
        if missing:
            failures.append(
                f"[{ref}] image manifest missing platforms: {missing} (found={sorted(platforms)}) oci={oci}"
            )

    if failures:
        msg = "Supply-chain failures:\n- " + "\n- ".join(failures)
        pytest.fail(msg)
