"""Container image operations (build, pin, push)."""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

import yaml
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.core.registry.loader import load_processor_spec, _registry_yaml_path_for_ref


# ============================================================================
# Shared utilities
# ============================================================================


def _print_json(payload: Dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


def _err(code: str, message: str, *, json_mode: bool) -> None:
    if json_mode:
        _print_json({"status": "error", "error": {"code": code, "message": message}})
    raise CommandError(f"{code}: {message}")


def _slugify_ref(ref: str) -> str:
    return ref.replace("/", "-").replace("@", "-")


def _detect_arch() -> str:
    """Normalize architecture to {'amd64','arm64'}."""
    machine = os.uname().machine
    if machine == "x86_64":
        return "amd64"
    if machine in ("arm64", "aarch64"):
        return "arm64"
    return machine


# ============================================================================
# Build subcommand
# ============================================================================


def _write_build_manifest(ref: str, tag_for_host: str) -> None:
    """Write build manifest for local image resolution."""
    try:
        ns, rest = ref.split("/", 1)
        name, ver = rest.split("@", 1)
    except ValueError:
        raise RuntimeError(f"Invalid ref '{ref}'. Expected ns/name@ver")

    # Use TOOLS_ROOTS from settings
    roots = getattr(settings, "TOOLS_ROOTS", [])
    if not roots:
        raise RuntimeError("TOOLS_ROOTS not configured in settings")

    tool_dir = roots[0] / ns / name / ver
    build_dir = tool_dir / ".build"
    build_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = build_dir / "manifest.json"
    arch = _detect_arch()
    now = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    data = {
        "ref": ref,
        "generated_at": now,
        "tags": {arch: tag_for_host},
        "latest_for_host": tag_for_host,
    }

    # Merge with existing manifest if present
    if manifest_path.exists():
        try:
            existing = json.loads(manifest_path.read_text())
            tags = existing.get("tags", {})
            tags[arch] = tag_for_host
            existing.update(
                {
                    "tags": tags,
                    "latest_for_host": tag_for_host,
                    "generated_at": now,
                }
            )
            data = existing
        except Exception:
            pass

    manifest_path.write_text(json.dumps(data, indent=2))


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

    try:
        ns, rest = ref.split("/", 1)
        name, ver = rest.split("@", 1)
    except ValueError:
        raise RuntimeError(f"invalid ref '{ref}', expected ns/name@ver")

    # Use TOOLS_ROOTS from settings
    roots = getattr(settings, "TOOLS_ROOTS", [])
    if not roots:
        raise RuntimeError("TOOLS_ROOTS not configured in settings")

    tool_dir = roots[0] / ns / name / ver

    context_path = Path(context)
    if not context_path.is_absolute():
        context_path = tool_dir / context_path

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
    except FileNotFoundError as exc:
        raise RuntimeError("Docker not found. Please install Docker.") from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr or exc.stdout or "<no output>"
        raise RuntimeError(f"docker build failed: {stderr}") from exc

    try:
        inspect_id = subprocess.run(
            ["docker", "image", "inspect", "--format={{.Id}}", image_tag],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
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
    except subprocess.CalledProcessError:
        image_digest = image_id

    return {
        "image_tag": image_tag,
        "image_id": image_id,
        "image_digest": image_digest,
    }


def cmd_build(args: argparse.Namespace) -> None:
    """Build tool image."""
    ref = args.ref
    platforms = args.platforms or f"linux/{_detect_arch()}"
    tag = getattr(args, "tag", None)
    no_cache = getattr(args, "no_cache", False)
    json_mode = getattr(args, "json", False)

    try:
        spec = load_processor_spec(ref)
    except FileNotFoundError as exc:
        _err("ERR_REGISTRY_MISSING", str(exc), json_mode=json_mode)
        return

    build_spec = spec.get("build") or {}
    try:
        result = _build_image(ref, build_spec, platforms=platforms, no_cache=no_cache, tag=tag)
        _write_build_manifest(ref, result["image_tag"])
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
        sys.stderr.write(
            "Built {ref}\n  tag={tag}\n  image_id={image_id}\n  digest={digest}\n".format(
                ref=ref,
                tag=payload["image_tag"],
                image_id=payload["image_id"],
                digest=payload["image_digest"],
            )
        )


# ============================================================================
# Pin subcommand
# ============================================================================

_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _resolve_yaml_path(ref: str) -> Path:
    """Resolve registry.yaml path using TOOLS_ROOTS from settings."""
    return _registry_yaml_path_for_ref(ref)


def _verify_digest(oci_ref: str) -> None:
    subprocess.run(["docker", "manifest", "inspect", oci_ref], check=True, capture_output=True, text=True)


def cmd_pin(args: argparse.Namespace) -> None:
    """Pin processor registry to OCI digest."""
    ref = args.ref
    oci = getattr(args, "oci", None)
    platform = getattr(args, "platform", None)
    verify = getattr(args, "verify_digest", False)
    json_mode = getattr(args, "json", False)

    if not oci:
        _err("ERR_PIN_ARGS", "--oci is required", json_mode=json_mode)
        return

    if not platform:
        _err("ERR_PIN_ARGS", "--platform is required (amd64 or arm64)", json_mode=json_mode)
        return

    try:
        yaml_path = _resolve_yaml_path(ref)
    except FileNotFoundError as exc:
        _err("ERR_REGISTRY_MISSING", str(exc), json_mode=json_mode)
        return

    if verify:
        try:
            _verify_digest(oci)
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr or exc.stdout or "<no output>"
            _err("ERR_IMAGE_UNAVAILABLE", f"Digest not found for {oci}: {stderr}", json_mode=json_mode)
            return

    try:
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        _err("ERR_REGISTRY_PIN", f"Failed to read YAML: {exc}", json_mode=json_mode)
        return

    image_section = data.setdefault("image", {})
    if "platforms" in image_section:
        platforms = image_section.get("platforms") or {}
        platforms[platform] = oci
        image_section["platforms"] = platforms
    else:
        image_section["oci"] = oci

    try:
        yaml_path.write_text(yaml.safe_dump(data, sort_keys=True, allow_unicode=True))
    except Exception as exc:
        _err("ERR_REGISTRY_PIN", f"Failed to write YAML: {exc}", json_mode=json_mode)
        return

    payload = {
        "status": "success",
        "ref": ref,
        "platform": platform,
        "pinned_oci": oci,
        "registry_yaml": str(yaml_path),
        "verified": verify,
    }

    if json_mode:
        _print_json(payload)
    else:
        sys.stderr.write(f"Pinned {ref} [{platform}] -> {oci}\n  file={yaml_path}\n  verified={verify}\n")


# ============================================================================
# Push subcommand
# ============================================================================


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=True)


def _docker_tag(image: str, target: str) -> None:
    _run(["docker", "tag", image, target])


def _docker_push(target: str) -> Dict[str, str]:
    try:
        result = _run(["docker", "push", target])
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr or exc.stdout or "<no output>"
        raise RuntimeError(f"docker push failed: {stderr}") from exc

    digest = None
    match = re.search(r"digest:\s*(sha256:[0-9a-f]{64})", result.stdout)
    if match:
        digest = match.group(1)
    else:
        inspect = _run(["docker", "image", "inspect", "--format={{index .RepoDigests 0}}", target])
        digest_ref = inspect.stdout.strip()
        if digest_ref and "@" in digest_ref:
            digest = digest_ref.split("@", 1)[1]

    if not digest:
        raise RuntimeError("Unable to determine pushed digest from docker output")

    repo = target.split(":", 1)[0]
    digest_ref = f"{repo}@{digest}"

    return {"pushed_digest": digest, "digest_ref": digest_ref}


def cmd_push(args: argparse.Namespace) -> None:
    """Push tool image to registry."""
    image = args.image
    target = args.target
    json_mode = getattr(args, "json", False)

    try:
        _docker_tag(image, target)
        push_info = _docker_push(target)
    except FileNotFoundError:
        _err("ERR_IMAGE_PUSH", "Docker not found. Please install Docker.", json_mode=json_mode)
        return
    except RuntimeError as exc:
        _err("ERR_IMAGE_PUSH", str(exc), json_mode=json_mode)
        return

    payload = {
        "status": "success",
        "image": image,
        "target": target,
        **push_info,
    }

    if json_mode:
        _print_json(payload)
    else:
        sys.stderr.write(
            "Pushed {target}\n  image={image}\n  digest={digest}\n".format(
                target=target,
                image=image,
                digest=push_info["pushed_digest"],
            )
        )


# ============================================================================
# Django Command
# ============================================================================


class Command(BaseCommand):
    help = "Container image operations: build, pin, push"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        sub = parser.add_subparsers(dest="subcmd", required=True)

        # build
        p_build = sub.add_parser("build", help="Build tool image")
        p_build.add_argument("--ref", required=True, help="Tool ref (e.g. llm/litellm@1)")
        p_build.add_argument(
            "--platforms",
            default=f"linux/{_detect_arch()}",
            help=f"Docker build platform (default: linux/{_detect_arch()})",
        )
        p_build.add_argument("--tag", help="Optional explicit image tag")
        p_build.add_argument("--no-cache", action="store_true", help="Disable Docker build cache")
        p_build.add_argument("--json", action="store_true", help="Emit machine JSON to stdout")
        p_build.set_defaults(func=cmd_build)

        # pin
        p_pin = sub.add_parser("pin", help="Pin registry to OCI digest")
        p_pin.add_argument("--ref", required=True, help="Tool ref (e.g. llm/litellm@1)")
        p_pin.add_argument("--oci", required=True, help="Full OCI reference (e.g. ghcr.io/org/repo@sha256:...)")
        p_pin.add_argument("--platform", required=True, help="Platform to pin (amd64 or arm64)")
        p_pin.add_argument("--verify-digest", action="store_true", help="Verify digest exists via docker manifest")
        p_pin.add_argument("--json", action="store_true", help="Emit machine JSON to stdout")
        p_pin.set_defaults(func=cmd_pin)

        # push
        p_push = sub.add_parser("push", help="Push image to registry")
        p_push.add_argument("--image", required=True, help="Local image reference (tag or ID)")
        p_push.add_argument("--target", required=True, help="Target repository:tag (e.g. ghcr.io/org/repo:tag)")
        p_push.add_argument("--json", action="store_true", help="Emit machine JSON to stdout")
        p_push.set_defaults(func=cmd_push)

    def handle(self, *args, **options):
        func = options.get("func")
        if not func:
            self.print_help("manage.py", "processorctl")
            return
        func(argparse.Namespace(**options))
