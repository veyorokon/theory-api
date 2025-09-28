"""Tag and push a local processor image to a container registry.

Stdout emits JSON when --json is passed; otherwise human-readable output goes to stderr.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from typing import Any, Dict

from django.core.management.base import BaseCommand, CommandError


def _print_json(payload: Dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


def _err(code: str, message: str, *, json_mode: bool) -> None:
    if json_mode:
        _print_json({"status": "error", "error": {"code": code, "message": message}})
    raise CommandError(f"{code}: {message}")


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=True)


def _docker_tag(image: str, target: str) -> None:
    _run(["docker", "tag", image, target])


def _docker_push(target: str) -> Dict[str, str]:
    try:
        result = _run(["docker", "push", target])
    except subprocess.CalledProcessError as exc:  # pragma: no cover
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


class Command(BaseCommand):
    help = "Push a locally built processor image to the registry"

    def add_arguments(self, parser):
        parser.add_argument("--image", required=True, help="Local image reference (tag or ID) to push")
        parser.add_argument(
            "--target",
            required=True,
            help="Target repository:tag (e.g. ghcr.io/org/theory-api/llm-litellm:dev-<stamp>)",
        )
        parser.add_argument("--json", action="store_true", help="Emit machine JSON to stdout")

    def handle(self, *args, **opts):
        image: str = opts["image"]
        target: str = opts["target"]
        json_mode: bool = bool(opts.get("json"))

        try:
            _docker_tag(image, target)
            push_info = _docker_push(target)
        except FileNotFoundError as exc:  # pragma: no cover
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
            self.stderr.write(
                "Pushed {target}\n  image={image}\n  digest={digest}".format(
                    target=target,
                    image=image,
                    digest=push_info["pushed_digest"],
                )
            )
