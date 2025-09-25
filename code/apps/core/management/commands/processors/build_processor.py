"""Build a processor image and report tag, image ID, and digest.

Outputs JSON to stdout when --json is provided; otherwise prints human
summary to stderr. Fails with stable error fragments so automation can parse
stderr when JSON is not requested.
"""

from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.core.registry.loader import load_processor_spec


def _print_json(payload: Dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


def _err(code: str, message: str, *, json_mode: bool) -> None:
    if json_mode:
        _print_json({"status": "error", "error": {"code": code, "message": message}})
    raise CommandError(f"{code}: {message}")


def _slugify_ref(ref: str) -> str:
    return ref.replace("/", "-").replace("@", "-")


def _build_image(
    ref: str, build_spec: Dict[str, Any], *, platforms: str, no_cache: bool, tag: str | None
) -> Dict[str, str]:
    if not build_spec:
        raise RuntimeError("No build specification found in registry entry")

    context = build_spec.get("context", ".")
    dockerfile = build_spec.get("dockerfile", "Dockerfile")
    default_tag = build_spec.get("tag")

    if tag:
        image_tag = tag
    elif default_tag:
        image_tag = default_tag
    else:
        slug = _slugify_ref(ref)
        stamp = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
        image_tag = f"theory-local/{slug}:build-{stamp}"

    # Resolve context relative to processor directory
    try:
        ns, rest = ref.split("/", 1)
        name, _ver = rest.split("@", 1)
    except ValueError:
        raise RuntimeError(f"invalid ref '{ref}', expected ns/name@ver")

    processor_dir = f"{ns}_{name}"
    processor_path = Path(settings.BASE_DIR) / "apps" / "core" / "processors" / processor_dir

    context_path = Path(context)
    if not context_path.is_absolute():
        context_path = processor_path / context_path

    if not context_path.exists():
        raise RuntimeError(f"Build context does not exist: {context_path}")

    dockerfile_path = context_path / dockerfile
    if not dockerfile_path.exists():
        raise RuntimeError(f"Dockerfile not found: {dockerfile_path}")

    platforms = platforms.strip()
    use_buildx = bool(platforms)

    if "," in platforms:
        raise RuntimeError("Multi-platform builds require push; specify a single platform")

    build_cmd: list[str]
    if use_buildx:
        build_cmd = [
            "docker",
            "buildx",
            "build",
            "--platform",
            platforms,
            "-t",
            image_tag,
            "-f",
            str(dockerfile_path),
        ]
        if no_cache:
            build_cmd.append("--no-cache")
        build_cmd.extend(["--load", str(context_path)])
    else:
        build_cmd = [
            "docker",
            "build",
            "-t",
            image_tag,
            "-f",
            str(dockerfile_path),
        ]
        if no_cache:
            build_cmd.append("--no-cache")
        build_cmd.append(str(context_path))

    try:
        subprocess.run(build_cmd, capture_output=True, text=True, check=True)
    except FileNotFoundError as exc:  # pragma: no cover (depends on local Docker)
        raise RuntimeError("Docker not found. Please install Docker.") from exc
    except subprocess.CalledProcessError as exc:  # pragma: no cover
        stderr = exc.stderr or exc.stdout or "<no output>"
        raise RuntimeError(f"docker build failed: {stderr}") from exc

    try:
        inspect_id = subprocess.run(
            ["docker", "image", "inspect", "--format={{.Id}}", image_tag],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:  # pragma: no cover
        raise RuntimeError(f"Failed to inspect built image {image_tag}: {exc.stderr}") from exc

    image_id = inspect_id.stdout.strip()

    try:
        inspect_digest = subprocess.run(
            ["docker", "image", "inspect", "--format={{index .RepoDigests 0}}", image_tag],
            capture_output=True,
            text=True,
            check=True,
        )
        digest_ref = inspect_digest.stdout.strip()
        if digest_ref and "@" in digest_ref:
            image_digest = digest_ref.split("@", 1)[1]
        else:
            image_digest = image_id
    except subprocess.CalledProcessError:  # pragma: no cover
        image_digest = image_id

    return {
        "image_tag": image_tag,
        "image_id": image_id,
        "image_digest": image_digest,
    }


class Command(BaseCommand):
    help = "Build processor image and report tag, image ID, and digest"

    def add_arguments(self, parser):
        parser.add_argument("--ref", required=True, help="Processor ref (e.g. llm/litellm@1)")
        parser.add_argument("--platforms", default="linux/amd64", help="Docker build platform (default: linux/amd64)")
        parser.add_argument("--tag", help="Optional explicit image tag to use when building")
        parser.add_argument("--no-cache", action="store_true", help="Disable Docker build cache")
        parser.add_argument("--json", action="store_true", help="Emit machine JSON to stdout")

    def handle(self, *args, **opts):
        ref: str = opts["ref"]
        platforms: str = opts["platforms"]
        tag: str | None = opts.get("tag")
        no_cache: bool = bool(opts.get("no_cache"))
        json_mode: bool = bool(opts.get("json"))

        try:
            spec = load_processor_spec(ref)
        except FileNotFoundError as exc:
            _err("ERR_REGISTRY_MISSING", str(exc), json_mode=json_mode)
            return

        build_spec = spec.get("build") or {}
        try:
            result = _build_image(ref, build_spec, platforms=platforms, no_cache=no_cache, tag=tag)
        except Exception as exc:
            _err("ERR_IMAGE_BUILD", str(exc), json_mode=json_mode)
            return

        payload = {
            "status": "success",
            "ref": ref,
            "platforms": platforms,
            **result,
        }

        if json_mode:
            _print_json(payload)
        else:
            self.stderr.write(
                "Built {ref}\n  tag={tag}\n  image_id={image_id}\n  digest={digest}".format(
                    ref=ref,
                    tag=payload["image_tag"],
                    image_id=payload["image_id"],
                    digest=payload["image_digest"],
                )
            )
