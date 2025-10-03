from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Dict, List, Tuple

import yaml
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

# --- Helpers ---------------------------------------------------------------


def _run(
    cmd: list[str], *, env: dict | None = None, check: bool = True, stdin: str | None = None
) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        cmd,
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
    )
    if check and proc.returncode != 0:
        raise CommandError(
            f"Command failed ({proc.returncode}): {' '.join(shlex.quote(c) for c in cmd)}\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    return proc


def _ensure_modal_cli():
    if not shutil.which("modal"):
        raise CommandError("Modal CLI not found. Install with: pip install modal-client")


def _require(val: str | None, msg: str) -> str:
    if not val:
        raise CommandError(msg)
    return val


def _modal_app_name(ref: str, env: str, branch: str | None, user: str | None) -> str:
    # Use shared naming logic from _modal_common
    from ._modal_common import modal_app_name

    if env == "dev":
        return modal_app_name(ref, env=env, branch=branch, user=user)
    else:
        return modal_app_name(ref, env=env)


def _write_temp_modal_script(source: str) -> Path:
    tmpdir = tempfile.mkdtemp(prefix="modalctl_")
    p = Path(tmpdir) / "modal_ephemeral.py"
    p.write_text(source)
    return p


def _digest_like(s: str) -> bool:
    return "@sha256:" in s and len(s.split("@sha256:")[-1]) >= 10


def _load_registry_for_ref(ref: str) -> dict:
    """
    Resolve registry.yaml path from ref (ns/name@ver) to:
    code/apps/core/processors/{ns}_{name}/registry.yaml
    """
    try:
        ns, rest = ref.split("/", 1)
        name, _ver = rest.split("@", 1)
    except ValueError as e:
        raise CommandError(f"Invalid ref '{ref}'. Expected ns/name@ver") from e

    root = Path(__file__).resolve().parents[4]  # .../code/
    reg_path = root / "apps" / "core" / "processors" / f"{ns}_{name}" / "registry.yaml"
    if not reg_path.exists():
        raise CommandError(f"registry.yaml not found for ref '{ref}' at {reg_path}")
    try:
        import yaml  # type: ignore
    except Exception as e:
        raise CommandError("PyYAML is required. Install with: pip install pyyaml") from e
    with reg_path.open("r") as f:
        return yaml.safe_load(f) or {}


# --- Sync-secrets helpers --------------------------------------------------


def _processor_dir(ref: str) -> Path:
    """Map ns/name@ver -> apps/core/processors/ns_name"""
    try:
        ns_name, _ver = ref.split("@", 1)
        ns, name = ns_name.split("/", 1)
    except ValueError:
        raise CommandError("Invalid --ref. Expected format: ns/name@ver")

    root = Path(__file__).resolve().parents[3]  # /code
    pdir = root / "apps" / "core" / "processors" / f"{ns}_{name}"
    if not pdir.exists():
        raise CommandError(f"Processor directory not found: {pdir}")
    return pdir


def _print_json(obj: dict):
    json.dump(obj, sys.stdout, separators=(",", ":"), sort_keys=True)
    sys.stdout.write("\n")
    sys.stdout.flush()


# --- Ephemeral modal scripts (SDK one-shots) -------------------------------


def _script_deploy(app_name: str, oci: str) -> str:
    digest_part = oci.split("@")[1] if "@" in oci else oci
    return textwrap.dedent(f"""
    import modal

    # Extend registry image with IMAGE_DIGEST env var
    base_image = modal.Image.from_registry("{oci}")
    image = base_image.env({{"IMAGE_DIGEST": "{digest_part}"}})

    app = modal.App("{app_name}", image=image)

    def cleanup_handler():
        # Modal exit handler to ensure clean shutdown
        # Prevents "background threads still running" warnings
        import asyncio
        import time
        print("[modal] Starting cleanup...")
        time.sleep(0.5)  # Give uvicorn time to shutdown gracefully
        print("[modal] Cleanup complete")

    @app.function(
        image=image,
        container_lifecycle={{"exit_handler": cleanup_handler}}
    )
    @modal.asgi_app()
    def fastapi_app():
        # Import the FastAPI app from the image at runtime
        # so Modal runs it directly as an ASGI application.
        from app.ws import app as fastapi_app
        return fastapi_app
    """)


def _script_status_json(app_name: str) -> str:
    return textwrap.dedent(f"""
    import json, modal

    def main():
        app = modal.App.lookup("{app_name}")
        data = {{"app": "{app_name}", "functions": []}}
        for fn_name in ["fastapi_app"]:
            try:
                fn = modal.Function.from_name(app.name, fn_name)
                ref = ""
                try:
                    ref = str(getattr(getattr(fn, "_function_image", None), "ref", "")) or str(getattr(fn, "image", ""))
                except Exception:
                    pass
                data["functions"].append({{"name": fn_name, "image_ref": ref}})
            except Exception as e:
                data["functions"].append({{"name": fn_name, "error": str(e)}})
        print(json.dumps(data))

    if __name__ == "__main__":
        main()
    """)


def _script_upsert_single_secret() -> str:
    # Reads JSON on stdin: {"name": "...", "value": "..."}
    # Creates/updates a Modal Secret with that name & single key-value.
    return textwrap.dedent("""
    import json, sys, modal
    payload = json.loads(sys.stdin.read())
    name = payload["name"]
    value = payload["value"]
    # Create secret with the key name same as secret name
    modal.Secret.objects.create(name, {name: value}, allow_existing=True)
    print(json.dumps({"status":"success","name":name}))
    """)


# --- Subcommand implementations --------------------------------------------


def cmd_deploy(args: argparse.Namespace) -> None:
    ref = _require(args.ref, "--ref is required (ns/name@ver)")
    env = _require(args.env, "--env is required (dev|staging|main)")
    oci = _require(args.oci, "--oci is required (ghcr.io/...@sha256:...)")
    if not _digest_like(oci):
        raise CommandError("Expected --oci in digest form: ghcr.io/owner/repo@sha256:...")

    app_name = _modal_app_name(
        ref=ref,
        env=env,
        branch=getattr(settings, "MODAL_BRANCH", None),
        user=getattr(settings, "MODAL_USER", None),
    )

    src = _script_deploy(app_name, oci)
    path = _write_temp_modal_script(src)

    _ensure_modal_cli()
    _run(["modal", "deploy", str(path), "--env", env])

    print(json.dumps({"status": "success", "app_name": app_name, "oci": oci, "env": env}))


def cmd_verify_digest(args: argparse.Namespace) -> None:
    ref = _require(args.ref, "--ref is required")
    env = _require(args.env, "--env is required")
    expected = _require(args.oci, "--oci is required")

    app_name = _modal_app_name(
        ref=ref,
        env=env,
        branch=getattr(settings, "MODAL_BRANCH", None),
        user=getattr(settings, "MODAL_USER", None),
    )

    src = _script_status_json(app_name)
    path = _write_temp_modal_script(src)

    _ensure_modal_cli()
    proc = _run([sys.executable, str(path)], check=True)
    try:
        data = json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception as e:
        raise CommandError(f"Could not parse status JSON:\n{proc.stdout}") from e

    bound = None
    for f in data.get("functions", []):
        if f.get("name") in ("http", "run", "default"):
            bound = f.get("image_ref") or bound

    ok = bound and expected in str(bound)
    result = {
        "app_name": app_name,
        "env": env,
        "expected_oci": expected,
        "bound_ref": bound or "",
        "match": bool(ok),
    }
    if not ok:
        raise CommandError(json.dumps({"status": "error", "code": "ERR_REGISTRY_MISMATCH", **result}))
    print(json.dumps({"status": "success", **result}))


def cmd_status(args: argparse.Namespace) -> None:
    ref = _require(args.ref, "--ref is required")
    env = _require(args.env, "--env is required")

    app_name = _modal_app_name(
        ref=ref,
        env=env,
        branch=getattr(settings, "MODAL_BRANCH", None),
        user=getattr(settings, "MODAL_USER", None),
    )

    src = _script_status_json(app_name)
    path = _write_temp_modal_script(src)

    _ensure_modal_cli()
    proc = _run([sys.executable, str(path)], check=True)
    sys.stdout.write(proc.stdout)


def cmd_logs(args: argparse.Namespace) -> None:
    ref = _require(args.ref, "--ref is required")
    env = _require(args.env, "--env is required")
    limit = str(args.limit or 50)

    app_name = _modal_app_name(
        ref=ref,
        env=env,
        branch=getattr(settings, "MODAL_BRANCH", None),
        user=getattr(settings, "MODAL_USER", None),
    )

    _ensure_modal_cli()
    cmd = ["modal", "app", "logs", app_name, "--env", env, "--limit", limit]
    if args.since:
        cmd += ["--since", args.since]
    if args.follow:
        cmd += ["--follow"]
    proc = subprocess.Popen(cmd)
    proc.wait()
    if proc.returncode != 0:
        raise CommandError(f"modal app logs failed with rc={proc.returncode}")


def _resolve_required_secret_names(ref: str) -> list[str]:
    reg = _load_registry_for_ref(ref)
    req = (((reg or {}).get("secrets") or {}).get("required")) or []
    if not isinstance(req, list):
        raise CommandError(f"Invalid registry.yaml: secrets.required should be a list. Got: {type(req)}")
    # coerce to unique, sorted
    names = sorted({str(x).strip() for x in req if str(x).strip()})
    return names


def cmd_sync_secrets(args: argparse.Namespace) -> None:
    ref = _require(args.ref, "--ref is required (ns/name@ver)")
    env = _require(args.env, "--env is required (dev|staging|main)")

    # 1) Figure out which secrets we need
    required = _resolve_required_secret_names(ref)
    if not required:
        print(json.dumps({"status": "success", "note": "no_required_secrets"}))
        return

    # 2) Collect from environment only
    kv: dict[str, str] = {}
    missing: list[str] = []

    for key in required:
        val = os.getenv(key)
        if val is None or str(val) == "":
            missing.append(key)
        else:
            kv[key] = str(val)

    # 3) Handle missing secrets
    if missing:
        result = {
            "status": "error",
            "code": "ERR_MISSING_SECRET",
            "ref": ref,
            "env": env,
            "missing": sorted(missing),
            "present": sorted(kv.keys()),
        }
        if hasattr(args, "json") and args.json:
            print(json.dumps(result))
        else:
            print(json.dumps(result, indent=2))
        raise CommandError(f"Missing required secrets: {', '.join(missing)}")

    # 4) Check mode - dry run
    if hasattr(args, "check") and args.check:
        result = {
            "status": "check",
            "ref": ref,
            "env": env,
            "would_sync": sorted(kv.keys()),
            "missing": [],
        }
        if hasattr(args, "json") and args.json:
            print(json.dumps(result))
        else:
            print(json.dumps(result, indent=2))
        return

    # 5) Actual sync - create individual secrets
    created = []
    updated = []
    unchanged = []

    for key, val in kv.items():
        # Create one Modal secret per key, named exactly as the env var
        payload = json.dumps({"name": key, "value": val})
        src = _script_upsert_single_secret()
        path = _write_temp_modal_script(src)

        try:
            proc = _run([sys.executable, str(path)], check=True, stdin=payload)
            # Parse result to categorize created/updated/unchanged
            if "created" in proc.stdout.lower():
                created.append(key)
            elif "updated" in proc.stdout.lower():
                updated.append(key)
            else:
                unchanged.append(key)
        except subprocess.CalledProcessError:
            result = {
                "status": "error",
                "code": "ERR_MODAL_SYNC",
                "ref": ref,
                "env": env,
                "failed_secret": key,
            }
            if hasattr(args, "json") and args.json:
                print(json.dumps(result))
            else:
                print(json.dumps(result, indent=2))
            raise CommandError(f"Failed to sync secret: {key}")

    # 6) Success result
    result = {
        "status": "success",
        "ref": ref,
        "env": env,
        "created": sorted(created),
        "updated": sorted(updated),
        "unchanged": sorted(unchanged),
    }
    if hasattr(args, "json") and args.json:
        print(json.dumps(result))
    else:
        print(json.dumps(result, indent=2))


# --- Django management command entrypoint -----------------------------------


class Command(BaseCommand):
    help = "Unified Modal control: deploy, verify-digest, status, logs, sync-secrets."

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        sub = parser.add_subparsers(dest="subcmd", required=True)

        # deploy
        p_deploy = sub.add_parser("deploy", help="Deploy app by OCI digest (digest-only).")
        p_deploy.add_argument("--ref", required=True, help="ns/name@ver")
        p_deploy.add_argument("--env", required=True, choices=["dev", "staging", "main"])
        p_deploy.add_argument("--oci", required=True, help="ghcr.io/...@sha256:...")
        p_deploy.set_defaults(func=cmd_deploy)

        # verify-digest
        p_verify = sub.add_parser("verify-digest", help="Verify bound image digest matches expected.")
        p_verify.add_argument("--ref", required=True)
        p_verify.add_argument("--env", required=True, choices=["dev", "staging", "main"])
        p_verify.add_argument("--oci", required=True)
        p_verify.set_defaults(func=cmd_verify_digest)

        # status
        p_status = sub.add_parser("status", help="Show app/functions and their bound images (JSON).")
        p_status.add_argument("--ref", required=True)
        p_status.add_argument("--env", required=True, choices=["dev", "staging", "main"])
        p_status.set_defaults(func=cmd_status)

        # logs
        p_logs = sub.add_parser("logs", help="Tail/print app logs.")
        p_logs.add_argument("--ref", required=True)
        p_logs.add_argument("--env", required=True, choices=["dev", "staging", "main"])
        p_logs.add_argument("--limit", type=int, default=50)
        p_logs.add_argument("--since", help="e.g. 10m, 1h")
        p_logs.add_argument("--follow", action="store_true")
        p_logs.set_defaults(func=cmd_logs)

        # sync-secrets
        p_sync = sub.add_parser("sync-secrets", help="Sync required secrets for processor")
        p_sync.add_argument("--ref", required=True, help="Processor ref: ns/name@ver")
        p_sync.add_argument("--env", required=True, help="Environment name (dev|staging|prod)")
        p_sync.add_argument("--check", action="store_true", help="Dry-run mode: show what would be synced")
        p_sync.add_argument("--prune", action="store_true", help="Remove extra secrets not in registry")
        p_sync.add_argument("--json", action="store_true", help="JSON output")
        p_sync.set_defaults(func=cmd_sync_secrets)

    def handle(self, *args, **options):
        return options["func"](argparse.Namespace(**options))
