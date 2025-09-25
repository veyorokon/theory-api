"""Pin a processor registry YAML entry to a specific OCI digest."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from django.core.management.base import BaseCommand, CommandError

from apps.core.registry.loader import get_registry_dir

_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _print_json(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload))


def _err(code: str, message: str, *, json_mode: bool) -> None:
    if json_mode:
        _print_json({"status": "error", "error": {"code": code, "message": message}})
    raise CommandError(f"{code}: {message}")


def _resolve_yaml_path(ref: str) -> Path:
    # New layout: code/apps/core/processors/<ns>_<name>/registry.yaml
    try:
        ns, rest = ref.split("/", 1)
        name, _ver = rest.split("@", 1)
    except ValueError as exc:
        raise FileNotFoundError(f"invalid ref '{ref}', expected ns/name@ver") from exc
    base = Path(get_registry_dir())  # returns processors root
    path = base / f"{ns}_{name}" / "registry.yaml"
    if not path.exists():
        raise FileNotFoundError(f"registry spec not found for {ref} at {path}")
    return path


def _verify_digest(oci_ref: str) -> None:
    subprocess.run(["docker", "manifest", "inspect", oci_ref], check=True, capture_output=True, text=True)


class Command(BaseCommand):
    help = "Update processor registry YAML with a pinned OCI digest"

    def add_arguments(self, parser):
        parser.add_argument("--ref", required=True, help="Processor ref (e.g. llm/litellm@1)")
        parser.add_argument(
            "--oci",
            help="Full OCI reference including digest (e.g. ghcr.io/org/repo@sha256:...)",
        )
        parser.add_argument("--repo", help="Repository prefix (used with --digest)")
        parser.add_argument("--digest", help="sha256 digest (used with --repo)")
        parser.add_argument(
            "--verify-digest", action="store_true", help="Verify digest exists via docker manifest inspect"
        )
        parser.add_argument("--json", action="store_true", help="Emit machine JSON to stdout")

    def handle(self, *args, **opts):
        ref: str = opts["ref"]
        oci: str | None = opts.get("oci")
        repo: str | None = opts.get("repo")
        digest: str | None = opts.get("digest")
        verify: bool = bool(opts.get("verify_digest"))
        json_mode: bool = bool(opts.get("json"))

        if not oci:
            if not (repo and digest):
                _err("ERR_PIN_ARGS", "Provide --oci or (--repo and --digest)", json_mode=json_mode)
                return
            if not _DIGEST_RE.match(digest):
                _err("ERR_PIN_ARGS", f"Invalid digest format: {digest}", json_mode=json_mode)
                return
            oci = f"{repo}@{digest}"

        try:
            yaml_path = _resolve_yaml_path(ref)
        except FileNotFoundError as exc:
            _err("ERR_REGISTRY_MISSING", str(exc), json_mode=json_mode)
            return

        if verify:
            try:
                _verify_digest(oci)
            except subprocess.CalledProcessError as exc:  # pragma: no cover
                stderr = exc.stderr or exc.stdout or "<no output>"
                _err("ERR_IMAGE_UNAVAILABLE", f"Digest not found for {oci}: {stderr}", json_mode=json_mode)
                return

        try:
            data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            _err("ERR_REGISTRY_PIN", f"Failed to read YAML: {exc}", json_mode=json_mode)
            return

        image_section = data.setdefault("image", {})
        # New schema supports platform digests; we still update a generic 'oci' if present
        # or set default_platform digest when only one digest is provided.
        if "platforms" in image_section:
            # update the default platform digest if it matches repo
            default_plat = image_section.get("default_platform", "amd64")
            platforms = image_section.get("platforms") or {}
            platforms[default_plat] = oci
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
            "pinned_oci": oci,
            "registry_yaml": str(yaml_path),
            "verified": verify,
        }

        if json_mode:
            _print_json(payload)
        else:
            self.stderr.write(f"Pinned {ref} -> {oci}\n  file={yaml_path}\n  verified={verify}")
