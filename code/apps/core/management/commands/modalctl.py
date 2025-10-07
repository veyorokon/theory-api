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
import uuid
from pathlib import Path
from typing import Dict, List, Tuple

import yaml
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from apps.core.utils import run_utils
from apps.core.management.utils import capture_stdout
from backend.middleware import logging as core_logging
from libs.runtime_common.envelope import resolve_mode, ModeSafetyError

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
    """Load registry.yaml using TOOLS_ROOTS from settings."""
    from apps.core.registry.loader import load_processor_spec

    try:
        return load_processor_spec(ref)
    except FileNotFoundError as e:
        raise CommandError(str(e)) from e


# --- Sync-secrets helpers --------------------------------------------------


def _tool_dir(ref: str) -> Path:
    """Map ns/name@ver -> <TOOLS_ROOT>/ns/name/ver"""
    from django.conf import settings

    try:
        ns, rest = ref.split("/", 1)
        name, ver = rest.split("@", 1)
    except ValueError:
        raise CommandError("Invalid --ref. Expected format: ns/name@ver")

    roots = settings.TOOLS_ROOTS
    if not roots:
        raise CommandError("TOOLS_ROOTS not configured in settings")

    pdir = roots[0] / ns / name / ver
    if not pdir.exists():
        raise CommandError(f"Tool directory not found: {pdir}")
    return pdir


def _print_json(obj: dict):
    json.dump(obj, sys.stdout, separators=(",", ":"), sort_keys=True)
    sys.stdout.write("\n")
    sys.stdout.flush()


# --- Ephemeral modal scripts (SDK one-shots) -------------------------------


def _script_deploy(app_name: str, oci: str, required_secrets: list[str], runtime_config: dict) -> str:
    digest_part = oci.split("@")[1] if "@" in oci else oci

    # Build secrets list for function decorator
    secrets_list = ", ".join([f'modal.Secret.from_name("{s}")' for s in required_secrets]) if required_secrets else ""
    secrets_param = f"secrets=[{secrets_list}]" if secrets_list else ""

    # Build runtime params
    cpu = runtime_config.get("cpu", "1")
    memory_mb = int(float(runtime_config.get("memory_gb", 2)) * 1024)
    timeout = runtime_config.get("timeout_s", 600)
    gpu = runtime_config.get("gpu")

    runtime_params = f"cpu={cpu}, memory={memory_mb}, timeout={timeout}"
    if gpu:
        runtime_params += f', gpu="{gpu}"'

    return textwrap.dedent(f"""
    import modal

    # Extend registry image with IMAGE_DIGEST env var
    base_image = modal.Image.from_registry("{oci}")
    image = base_image.env({{"IMAGE_DIGEST": "{digest_part}"}})

    app = modal.App("{app_name}", image=image)

    @app.function(image=image, {runtime_params}{", " + secrets_param if secrets_param else ""})
    @modal.asgi_app()
    def fastapi_app():
        # Import the FastAPI app from the image at runtime
        # so Modal runs it directly as an ASGI application.
        from protocol.ws import app as fastapi_app
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


def cmd_start(args: argparse.Namespace, stdout=None) -> None:
    ref = _require(args.ref, "--ref is required (ns/name@ver)")
    oci = args.oci  # Optional now

    # Load registry to get both oci (if needed) and required secrets
    reg = _load_registry_for_ref(ref)

    # If --oci not provided, read from registry.yaml
    if not oci:
        image = reg.get("image") or {}
        platforms = image.get("platforms") or {}
        oci = platforms.get("amd64")  # Modal always uses amd64
        if not oci:
            raise CommandError(
                f"No amd64 platform pinned in registry.yaml for {ref}. Run 'imagectl pin --ref {ref} --platform amd64' first."
            )

    if not _digest_like(oci):
        raise CommandError("Expected --oci in digest form: ghcr.io/owner/repo@sha256:...")

    # Get required secrets
    required_secrets = _resolve_required_secret_names(ref)

    # Get runtime config
    runtime_config = reg.get("runtime", {})

    env = settings.MODAL_ENVIRONMENT
    app_name = _modal_app_name(
        ref=ref,
        env=env,
        branch=settings.GIT_BRANCH,
        user=settings.GIT_USER,
    )

    src = _script_deploy(app_name, oci, required_secrets, runtime_config)
    path = _write_temp_modal_script(src)

    _ensure_modal_cli()
    _run(["modal", "deploy", str(path), "--env", env])

    print(json.dumps({"status": "success", "app_name": app_name, "oci": oci, "env": env, "secrets": required_secrets}))


def cmd_stop(args: argparse.Namespace, stdout=None) -> None:
    ref = _require(args.ref, "--ref is required")

    env = settings.MODAL_ENVIRONMENT
    app_name = _modal_app_name(
        ref=ref,
        env=env,
        branch=settings.GIT_BRANCH,
        user=settings.GIT_USER,
    )

    _ensure_modal_cli()
    _run(["modal", "app", "stop", app_name, "--env", env])

    print(json.dumps({"status": "success", "app_name": app_name, "env": env}))


@capture_stdout
def cmd_status(args: argparse.Namespace) -> dict:
    """Show app/functions status including web URL."""
    from apps.core.utils.adapters import get_modal_web_url

    ref = _require(args.ref, "--ref is required")

    env = settings.MODAL_ENVIRONMENT
    app_name = _modal_app_name(
        ref=ref,
        env=env,
        branch=settings.GIT_BRANCH,
        user=settings.GIT_USER,
    )

    src = _script_status_json(app_name)
    path = _write_temp_modal_script(src)

    _ensure_modal_cli()
    proc = _run([sys.executable, str(path)], check=True)
    status_data = json.loads(proc.stdout)

    # Add URL to status
    try:
        url = get_modal_web_url(app_name, "tool_func")
        status_data["url"] = url
    except Exception:
        status_data["url"] = None

    return status_data


def cmd_logs(args: argparse.Namespace, stdout=None) -> None:
    ref = _require(args.ref, "--ref is required")
    limit = str(args.limit or 50)

    env = settings.MODAL_ENVIRONMENT
    app_name = _modal_app_name(
        ref=ref,
        env=env,
        branch=settings.GIT_BRANCH,
        user=settings.GIT_USER,
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


def cmd_sync_secrets(args: argparse.Namespace, stdout=None) -> None:
    ref = _require(args.ref, "--ref is required (ns/name@ver)")
    env = settings.MODAL_ENVIRONMENT

    # 1) Figure out which secrets we need
    required = _resolve_required_secret_names(ref)
    if not required:
        print(json.dumps({"status": "success", "note": "no_required_secrets"}))
        return

    # 2) Collect from environment only
    kv: dict[str, str] = {}
    missing: list[str] = []
    mock_missing = getattr(args, "mock_missing_secrets", False)

    for key in required:
        val = os.getenv(key)
        if val is None or str(val) == "":
            if mock_missing:
                kv[key] = f"sk-mock-{key.lower()}"
            else:
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


def cmd_run(args: argparse.Namespace, stdout=None) -> None:
    """Run tool with modal adapter."""
    # Support both run_id and execution_id during transition
    run_id = str(uuid.uuid4())

    if args.json:
        os.environ["LOG_STREAM"] = "stderr"

    # Bind logging context
    core_logging.bind(
        trace_id=run_id,
        tool_ref=args.ref,
        adapter="modal",
        mode=args.mode or "mock",
    )

    try:
        # Require {run_id} in write prefix (support both forms during transition)
        write_prefix = args.write_prefix
        if write_prefix and "{run_id}" not in write_prefix and "{execution_id}" not in write_prefix:
            raise CommandError("--write-prefix must include '{run_id}' to prevent output collisions")

        # Parse inputs
        inputs_json = run_utils.parse_inputs(vars(args))

        # Inject mode
        if args.mode:
            inputs_json["mode"] = args.mode
        elif os.environ.get("CI") == "true" and "mode" not in inputs_json:
            inputs_json["mode"] = "mock"

        # Validate mode
        try:
            resolve_mode(args.mode)
        except ModeSafetyError as e:
            core_logging.error(
                "execution.fail",
                error={"code": "ERR_CI_SAFETY", "message": e.message},
                reason="ci_guardrail_block",
                ci=True,
                mode="real",
            )
            sys.stderr.write(f"Error: {e.message}\n")
            sys.exit(1)
        except Exception as e:
            core_logging.error("execution.fail", error={"code": "ERR_MODE_INVALID", "message": str(e)})
            sys.stderr.write(f"Error: {e}\n")
            sys.exit(1)

        # Materialize attachments
        attachment_map = {}
        if args.attach:
            try:
                attachment_map = run_utils.materialize_attachments(args.attach)
                if not args.json:
                    for name, info in attachment_map.items():
                        sys.stdout.write(f"Materialized {name} -> {info.get('$artifact')} ({info.get('cid')})\n")
            except (ValueError, FileNotFoundError) as e:
                sys.stderr.write(f"Error: {e}\n")
                sys.exit(1)

        # Rewrite $attach references
        if attachment_map:
            try:
                inputs_json = run_utils.rewrite_attach_references(inputs_json, attachment_map)
            except ValueError as e:
                sys.stderr.write(f"Error: {e}\n")
                sys.exit(1)

        # Invoke processor with modal adapter
        from apps.core.tool_runner import ToolRunner

        # Determine artifact scope from storage backend
        artifact_scope = "world" if settings.STORAGE_BACKEND == "s3" else "local"

        runner = ToolRunner()
        result = runner.invoke(
            ref=args.ref,
            mode=args.mode,
            inputs=inputs_json,
            stream=False,
            timeout_s=args.timeout or 600,
            run_id=run_id,
            write_prefix=write_prefix,
            adapter="modal",
            artifact_scope=artifact_scope,
        )

        # Download outputs if requested
        if result.get("status") == "success" and result.get("outputs"):
            try:
                if args.save_dir:
                    run_utils.download_all_outputs(result["outputs"], args.save_dir)
                    if not args.json:
                        sys.stdout.write(f"Downloaded outputs to {args.save_dir}\n")
                elif args.save_first:
                    run_utils.download_first_output(result["outputs"], args.save_first)
                    if not args.json:
                        sys.stdout.write(f"Downloaded first output to {args.save_first}\n")
            except Exception as e:
                sys.stderr.write(f"Error downloading outputs: {e}\n")

        # Output JSON
        sys.stdout.write(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")

    finally:
        core_logging.clear()


# --- Django management command entrypoint -----------------------------------


class Command(BaseCommand):
    help = "Unified Modal control: start, stop, status, logs, run, sync-secrets."

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        sub = parser.add_subparsers(dest="subcmd", required=True)

        # start
        p_start = sub.add_parser("start", help="Start (deploy) app")
        p_start.add_argument("--ref", required=True, help="ns/name@ver")
        p_start.add_argument("--oci", help="ghcr.io/...@sha256:... (default: read from registry.yaml)")
        p_start.add_argument(
            "--mock-missing-secrets", action="store_true", help="Generate mock values for missing required secrets"
        )
        p_start.set_defaults(func=cmd_start)

        # stop
        p_stop = sub.add_parser("stop", help="Stop (delete) deployed app")
        p_stop.add_argument("--ref", required=True, help="ns/name@ver")
        p_stop.set_defaults(func=cmd_stop)

        # status
        p_status = sub.add_parser("status", help="Show app/functions status with URL (JSON)")
        p_status.add_argument("--ref", required=True, help="ns/name@ver")
        p_status.set_defaults(func=cmd_status)

        # logs
        p_logs = sub.add_parser("logs", help="Tail/print app logs")
        p_logs.add_argument("--ref", required=True, help="ns/name@ver")
        p_logs.add_argument("--limit", type=int, default=50, help="Number of log lines")
        p_logs.add_argument("--since", help="e.g. 10m, 1h")
        p_logs.add_argument("--follow", "-f", action="store_true", help="Follow log output")
        p_logs.set_defaults(func=cmd_logs)

        # run
        p_run = sub.add_parser("run", help="Run tool with modal adapter")
        p_run.add_argument("--ref", required=True, help="Tool ref (e.g., llm/litellm@1)")
        p_run.add_argument("--mode", choices=["real", "mock"], help="Tool mode")
        p_run.add_argument("--write-prefix", help="Write prefix for outputs (must include {run_id})")
        p_run.add_argument("--timeout", type=int, help="Timeout in seconds (default: 600)")
        p_run.add_argument("--json", action="store_true", help="Output JSON response")

        # Input options (mutually exclusive)
        inputs_group = p_run.add_mutually_exclusive_group()
        inputs_group.add_argument("--inputs-json", help="JSON input (no escaping required)")
        inputs_group.add_argument("--inputs-file", help="Read JSON input from file")
        inputs_group.add_argument("--inputs", help="Read JSON from stdin (use '-')")
        inputs_group.add_argument("--inputs-jsonstr", default="{}", help="JSON input as string (legacy)")

        # Attachment and output options
        p_run.add_argument("--attach", action="append", help="Attach file as name=path (can be used multiple times)")
        p_run.add_argument("--save-dir", help="Download all outputs into this directory")
        p_run.add_argument("--save-first", help="Download only the first output into this file")
        p_run.set_defaults(func=cmd_run)

        # sync-secrets
        p_sync = sub.add_parser("sync-secrets", help="Sync required secrets for tool")
        p_sync.add_argument("--ref", required=True, help="Tool ref: ns/name@ver")
        p_sync.add_argument("--check", action="store_true", help="Dry-run mode: show what would be synced")
        p_sync.add_argument("--prune", action="store_true", help="Remove extra secrets not in registry")
        p_sync.add_argument("--json", action="store_true", help="JSON output")
        p_sync.set_defaults(func=cmd_sync_secrets)

    def handle(self, *args, **options):
        return options["func"](argparse.Namespace(**options), stdout=self.stdout)
