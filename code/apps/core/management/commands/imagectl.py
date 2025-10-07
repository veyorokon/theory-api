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


def _require(val: str | None, msg: str) -> str:
    if not val:
        raise CommandError(msg)
    return val


def _normalize_platform(platform: str) -> str:
    """Normalize platform string to amd64 or arm64."""
    # Strip linux/ prefix if present
    if platform.startswith("linux/"):
        platform = platform[6:]

    if platform in ("amd64", "x86_64"):
        return "amd64"
    if platform in ("arm64", "aarch64"):
        return "arm64"

    return platform


def _read_build_manifest(ref: str) -> Dict[str, Any]:
    """Read build manifest for ref."""
    try:
        ns, rest = ref.split("/", 1)
        name, ver = rest.split("@", 1)
    except ValueError:
        raise RuntimeError(f"Invalid ref '{ref}'. Expected ns/name@ver")

    roots = settings.TOOLS_ROOTS
    if not roots:
        raise RuntimeError("TOOLS_ROOTS not configured in settings")

    tool_dir = roots[0] / ns / name / ver
    manifest_path = tool_dir / ".build" / "manifest.json"

    if not manifest_path.exists():
        raise RuntimeError(f"Build manifest not found: {manifest_path}. Run 'imagectl build' first.")

    with open(manifest_path) as f:
        return json.load(f)


def _get_latest_tag(ref: str, platform: str | None = None) -> str:
    """Get latest build tag from manifest."""
    manifest = _read_build_manifest(ref)
    if platform:
        tag = manifest.get("tags", {}).get(platform)
        if not tag:
            raise RuntimeError(f"No build found for platform {platform}")
        return tag
    return manifest.get("latest_for_host", "")


def _construct_remote_path(ref: str) -> str:
    """Transform ref to remote registry path."""
    try:
        ns, rest = ref.split("/", 1)
        name, ver = rest.split("@", 1)
    except ValueError:
        raise RuntimeError(f"Invalid ref '{ref}'. Expected ns/name@ver")

    host = settings.REGISTRY_HOST
    org = settings.REGISTRY_ORG
    # llm/litellm@1 → ghcr.io/veyorokon/theory-api/llm-litellm
    return f"{host}/{org}/theory-api/{ns}-{name}"


def _get_digest_for_tag(image_tag: str) -> str:
    """Get digest for local or remote tag."""
    # Try local inspect first
    try:
        result = subprocess.run(
            ["docker", "image", "inspect", "--format={{index .RepoDigests 0}}", image_tag],
            capture_output=True,
            text=True,
            check=True,
        )
        digest_ref = result.stdout.strip()
        if digest_ref and "@" in digest_ref:
            return digest_ref.split("@", 1)[1]
    except subprocess.CalledProcessError:
        pass

    # Fall back to manifest inspect (remote)
    try:
        result = subprocess.run(
            ["docker", "manifest", "inspect", image_tag], capture_output=True, text=True, check=True
        )
        manifest = json.loads(result.stdout)
        # Extract digest from config
        if "config" in manifest and "digest" in manifest["config"]:
            return manifest["config"]["digest"]
        # Or from manifest digest
        result2 = subprocess.run(
            ["docker", "manifest", "inspect", "--verbose", image_tag], capture_output=True, text=True, check=True
        )
        import re

        match = re.search(r'"digest":\s*"(sha256:[0-9a-f]{64})"', result2.stdout)
        if match:
            return match.group(1)
    except subprocess.CalledProcessError:
        pass

    raise RuntimeError(f"Unable to determine digest for {image_tag}")


# ============================================================================
# Build subcommand
# ============================================================================


def _write_build_manifest(ref: str, platform: str, tag_for_host: str) -> None:
    """Write build manifest for local image resolution."""
    try:
        ns, rest = ref.split("/", 1)
        name, ver = rest.split("@", 1)
    except ValueError:
        raise RuntimeError(f"Invalid ref '{ref}'. Expected ns/name@ver")

    # Use TOOLS_ROOTS from settings
    roots = settings.TOOLS_ROOTS
    if not roots:
        raise RuntimeError("TOOLS_ROOTS not configured in settings")

    tool_dir = roots[0] / ns / name / ver
    build_dir = tool_dir / ".build"
    build_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = build_dir / "manifest.json"
    arch = _normalize_platform(platform)
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

    dockerfile = build_spec.get("dockerfile", "Dockerfile")
    default_tag = build_spec.get("tag")

    if tag:
        image_tag = tag
    elif default_tag:
        image_tag = default_tag
    else:
        slug = _slugify_ref(ref)
        stamp = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
        image_tag = f"{settings.LOCAL_REGISTRY_PREFIX}{slug}:build-{stamp}"

    try:
        ns, rest = ref.split("/", 1)
        name, ver = rest.split("@", 1)
    except ValueError:
        raise RuntimeError(f"invalid ref '{ref}', expected ns/name@ver")

    # Use TOOLS_ROOTS from settings
    roots = settings.TOOLS_ROOTS
    if not roots:
        raise RuntimeError("TOOLS_ROOTS not configured in settings")

    tool_dir = roots[0] / ns / name / ver

    # Always use project root as build context to access code/libs
    project_root = settings.BASE_DIR.parent
    context_path = project_root

    if not context_path.exists():
        raise RuntimeError(f"Build context does not exist: {context_path}")

    # Dockerfile path is relative to tool directory
    dockerfile_path = tool_dir / dockerfile
    if not dockerfile_path.exists():
        raise RuntimeError(f"Dockerfile not found: {dockerfile_path}")

    platforms = platforms.strip()
    # Add linux/ prefix if not present
    if platforms and not platforms.startswith("linux/"):
        platforms = f"linux/{platforms}"
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
    platform = _require(args.platform, "--platform is required (amd64 or arm64)")
    platforms = f"linux/{_normalize_platform(platform)}"
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
        _write_build_manifest(ref, platform, result["image_tag"])
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


def _update_registry_yaml(ref: str, platform: str, oci: str) -> Path:
    """Update registry.yaml with pinned digest."""
    yaml_path = _resolve_yaml_path(ref)
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}

    image_section = data.setdefault("image", {})
    if "platforms" in image_section:
        platforms = image_section.get("platforms") or {}
        platforms[platform] = oci
        image_section["platforms"] = platforms
    else:
        image_section["oci"] = oci

    yaml_path.write_text(yaml.safe_dump(data, sort_keys=True, allow_unicode=True))
    return yaml_path


def cmd_pin(args: argparse.Namespace) -> None:
    """Pin digest in registry.yaml with minimal args."""
    ref = args.ref
    tag = getattr(args, "tag", None)
    platform = _normalize_platform(_require(args.platform, "--platform is required (amd64 or arm64)"))
    verify = getattr(args, "verify_digest", False)
    json_mode = getattr(args, "json", False)

    try:
        # Detect local vs remote image
        if tag and tag.startswith(settings.LOCAL_REGISTRY_PREFIX):
            # Local image - write tag directly without digest resolution
            oci_ref = tag
        else:
            # Remote image - resolve digest
            if tag:
                # User specified explicit tag - look it up
                remote_path = _construct_remote_path(ref)
                full_tag = f"{remote_path}:{tag}"
                digest = _get_digest_for_tag(full_tag)
            else:
                # Use latest from manifest
                source_tag = _get_latest_tag(ref, platform)
                digest = _get_digest_for_tag(source_tag)

            # Construct OCI ref
            remote_path = _construct_remote_path(ref)
            oci_ref = f"{remote_path}@{digest}"

            # Verify if requested
            if verify:
                try:
                    _verify_digest(oci_ref)
                except subprocess.CalledProcessError as exc:
                    stderr = exc.stderr or exc.stdout or "<no output>"
                    _err("ERR_IMAGE_UNAVAILABLE", f"Digest not found for {oci_ref}: {stderr}", json_mode=json_mode)
                    return

        # Update registry.yaml
        yaml_path = _update_registry_yaml(ref, platform, oci_ref)

        payload = {
            "status": "success",
            "ref": ref,
            "platform": platform,
            "pinned_oci": oci_ref,
            "registry_yaml": str(yaml_path),
            "verified": verify if not (tag and tag.startswith(settings.LOCAL_REGISTRY_PREFIX)) else False,
        }

        if json_mode:
            _print_json(payload)
        else:
            sys.stderr.write(f"Pinned {ref} [{platform}]\n  oci={oci_ref}\n  file={yaml_path}\n")

    except FileNotFoundError as exc:
        _err("ERR_REGISTRY_MISSING", str(exc), json_mode=json_mode)
    except RuntimeError as exc:
        _err("ERR_REGISTRY_PIN", str(exc), json_mode=json_mode)


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
    """Push tool image to registry with minimal args."""
    ref = args.ref
    tag = getattr(args, "tag", None)
    platform = _normalize_platform(_require(args.platform, "--platform is required (amd64 or arm64)"))
    json_mode = getattr(args, "json", False)

    try:
        # Get source tag
        if not tag:
            source_tag = _get_latest_tag(ref, platform)
        else:
            # User specified explicit tag
            source_tag = tag

        # Construct target path
        remote_path = _construct_remote_path(ref)
        # Extract timestamp/tag from source (e.g., theory-local/llm-litellm-1:build-20251006182555)
        tag_suffix = source_tag.split(":")[-1] if ":" in source_tag else "latest"
        target = f"{remote_path}:{tag_suffix}"

        # Push
        _docker_tag(source_tag, target)
        push_info = _docker_push(target)

        payload = {
            "status": "success",
            "ref": ref,
            "source": source_tag,
            "target": target,
            "platform": platform,
            **push_info,
        }

        if json_mode:
            _print_json(payload)
        else:
            sys.stderr.write(
                f"Pushed {ref} [{platform}]\n  source={source_tag}\n  target={target}\n  digest={push_info['pushed_digest']}\n"
            )

    except FileNotFoundError:
        _err("ERR_IMAGE_PUSH", "Docker not found. Please install Docker.", json_mode=json_mode)
    except RuntimeError as exc:
        _err("ERR_IMAGE_PUSH", str(exc), json_mode=json_mode)


# ============================================================================
# Publish subcommand (push + pin)
# ============================================================================


def cmd_publish(args: argparse.Namespace) -> None:
    """Push and pin in one command."""
    json_mode = getattr(args, "json", False)

    # Push first
    cmd_push(args)

    # Then pin (will use the digest we just pushed)
    cmd_pin(args)

    if not json_mode:
        sys.stderr.write(f"\n\u2713 Published {args.ref}\n")
        sys.stderr.write(f"Ready to deploy: python manage.py modalctl start --ref {args.ref}\n")


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
        p_build.add_argument("--platform", required=True, help="Platform (amd64 or arm64)")
        p_build.add_argument("--tag", help="Optional explicit image tag")
        p_build.add_argument("--no-cache", action="store_true", help="Disable Docker build cache")
        p_build.add_argument("--json", action="store_true", help="Emit machine JSON to stdout")
        p_build.set_defaults(func=cmd_build)

        # push
        p_push = sub.add_parser("push", help="Push image to registry")
        p_push.add_argument("--ref", required=True, help="Tool ref (e.g. llm/litellm@1)")
        p_push.add_argument("--platform", required=True, help="Platform (amd64 or arm64)")
        p_push.add_argument("--tag", help="Explicit tag (default: latest from manifest)")
        p_push.add_argument("--json", action="store_true", help="Emit machine JSON to stdout")
        p_push.set_defaults(func=cmd_push)

        # pin
        p_pin = sub.add_parser("pin", help="Pin digest in registry.yaml")
        p_pin.add_argument("--ref", required=True, help="Tool ref (e.g. llm/litellm@1)")
        p_pin.add_argument("--platform", required=True, help="Platform (amd64 or arm64)")
        p_pin.add_argument("--tag", help="Tag to pin (default: latest from manifest)")
        p_pin.add_argument("--verify-digest", action="store_true", help="Verify digest exists via docker manifest")
        p_pin.add_argument("--json", action="store_true", help="Emit machine JSON to stdout")
        p_pin.set_defaults(func=cmd_pin)

        # publish
        p_publish = sub.add_parser("publish", help="Push and pin in one command")
        p_publish.add_argument("--ref", required=True, help="Tool ref (e.g. llm/litellm@1)")
        p_publish.add_argument("--platform", required=True, help="Platform (amd64 or arm64)")
        p_publish.add_argument("--json", action="store_true", help="Emit machine JSON to stdout")
        p_publish.set_defaults(func=cmd_publish)

    def handle(self, *args, **options):
        func = options.get("func")
        if not func:
            self.print_help("manage.py", "processorctl")
            return
        func(argparse.Namespace(**options))
