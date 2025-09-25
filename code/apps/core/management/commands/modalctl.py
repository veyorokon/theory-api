from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Optional

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


# --- Ephemeral modal scripts (SDK one-shots) -------------------------------


def _script_deploy(app_name: str, oci: str) -> str:
    digest_part = oci.split("@")[1] if "@" in oci else oci
    return textwrap.dedent(f"""
    import modal

    # Extend registry image with IMAGE_DIGEST env var
    base_image = modal.Image.from_registry("{oci}")
    image = base_image.env({{"IMAGE_DIGEST": "{digest_part}"}})

    app = modal.App("{app_name}", image=image)

    @app.function(image=image)
    @modal.asgi_app()
    def fastapi_app():
        # Import the FastAPI app from the image at runtime
        # so Modal runs it directly as an ASGI application.
        from app.http import app as fastapi_app
        return fastapi_app
    """)


def _script_status_json(app_name: str) -> str:
    return textwrap.dedent(f"""
    import json, modal

    app = modal.App.lookup("{app_name}")
    data = {{"app": "{app_name}", "functions": []}}
    for fn_name in ["http", "run", "default"]:
        try:
            fn = app[fn_name]  # Direct lookup by name
            ref = ""
            try:
                ref = str(getattr(getattr(fn, "_function_image", None), "ref", "")) or str(getattr(fn, "image", ""))
            except Exception:
                pass
            data["functions"].append({{"name": fn_name, "image_ref": ref}})
        except Exception:
            pass
    print(json.dumps(data))
    """)


def _script_upsert_secret() -> str:
    # Reads JSON on stdin: {"name": "...", "kv": {...}}
    # Creates/updates a Modal Secret with that name & key-values.
    return textwrap.dedent("""
    import json, sys, modal
    payload = json.loads(sys.stdin.read())
    name = payload["name"]
    kv = payload["kv"]
    # Overwrite semantics: persist will replace existing secret with same name
    modal.Secret.from_dict(kv).persist(name)
    print(json.dumps({"status":"success","name":name,"keys":sorted(list(kv.keys()))}))
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
        branch=os.getenv("GITHUB_HEAD_REF") or os.getenv("BRANCH"),
        user=os.getenv("USER") or os.getenv("BUILD_USER"),
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
        branch=os.getenv("GITHUB_HEAD_REF") or os.getenv("BRANCH"),
        user=os.getenv("USER") or os.getenv("BUILD_USER"),
    )

    src = _script_status_json(app_name)
    path = _write_temp_modal_script(src)

    _ensure_modal_cli()
    proc = _run(["python", str(path)], check=True)
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
        branch=os.getenv("GITHUB_HEAD_REF") or os.getenv("BRANCH"),
        user=os.getenv("USER") or os.getenv("BUILD_USER"),
    )

    src = _script_status_json(app_name)
    path = _write_temp_modal_script(src)

    _ensure_modal_cli()
    proc = _run(["modal", "run", str(path)], check=True)
    sys.stdout.write(proc.stdout)


def cmd_logs(args: argparse.Namespace) -> None:
    ref = _require(args.ref, "--ref is required")
    env = _require(args.env, "--env is required")
    limit = str(args.limit or 50)

    app_name = _modal_app_name(
        ref=ref,
        env=env,
        branch=os.getenv("GITHUB_HEAD_REF") or os.getenv("BRANCH"),
        user=os.getenv("USER") or os.getenv("BUILD_USER"),
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


def _load_overrides_from_json(path: str | None) -> dict[str, str]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        raise CommandError(f"--from-json file not found: {p}")
    try:
        data = json.loads(p.read_text())
    except Exception as e:
        raise CommandError(f"--from-json must be valid JSON object: {e}") from e
    if not isinstance(data, dict):
        raise CommandError("--from-json must be a JSON object of KEY: VALUE")
    # coerce values to strings
    return {k: str(v) for k, v in data.items()}


def cmd_sync_secrets(args: argparse.Namespace) -> None:
    ref = _require(args.ref, "--ref is required (ns/name@ver)")
    env = _require(args.env, "--env is required (dev|staging|main)")

    # 1) Figure out which secrets we need
    required = _resolve_required_secret_names(ref)
    if not required:
        print(json.dumps({"status": "success", "note": "no_required_secrets"}))
        return

    # 2) Load overrides from JSON (optional), then fill from environment
    overrides = _load_overrides_from_json(args.from_json)
    kv: dict[str, str] = {}
    missing: list[str] = []

    for key in required:
        if key in overrides and overrides[key] is not None:
            kv[key] = str(overrides[key])
            continue
        val = os.getenv(key)
        if val is None or str(val) == "":
            missing.append(key)
        else:
            kv[key] = str(val)

    if missing and not args.allow_missing:
        raise CommandError(
            json.dumps(
                {
                    "status": "error",
                    "code": "ERR_MISSING_SECRET",
                    "missing": missing,
                    "present": sorted(kv.keys()),
                    "hint": "Provide via environment or --from-json",
                }
            )
        )

    # If some are missing but allowed, proceed with the ones we have
    if args.dry_run:
        print(
            json.dumps(
                {
                    "status": "dry_run",
                    "would_sync": sorted(kv.keys()),
                    "missing": missing,
                    "ref": ref,
                    "env": env,
                }
            )
        )
        return

    # 3) Choose a canonical secret name (overridable)
    app_name = _modal_app_name(
        ref=ref,
        env=env,
        branch=os.getenv("GITHUB_HEAD_REF") or os.getenv("BRANCH"),
        user=os.getenv("USER") or os.getenv("BUILD_USER"),
    )
    secret_name = args.name or f"{app_name}-secrets"

    # 4) Upsert via a tiny SDK script
    payload = json.dumps({"name": secret_name, "kv": kv})
    src = _script_upsert_secret()
    path = _write_temp_modal_script(src)

    _ensure_modal_cli()
    # We don't need a specific env for secret ops, but we allow passing one for consistency
    proc = _run(["modal", "run", str(path)], check=True, stdin=payload)

    # 5) Emit a boring, structured result
    print(
        json.dumps(
            {
                "status": "success",
                "ref": ref,
                "env": env,
                "secret": secret_name,
                "synced_keys": sorted(kv.keys()),
                "missing": missing,
            }
        )
    )


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
        p_sync = sub.add_parser("sync-secrets", help="Create/update Modal Secret from registry required keys.")
        p_sync.add_argument("--ref", required=True, help="ns/name@ver")
        p_sync.add_argument("--env", required=True, choices=["dev", "staging", "main"])
        p_sync.add_argument("--name", help="Modal Secret name (default: <app-name>-secrets)")
        p_sync.add_argument("--from-json", help="Path to JSON file with KEY: VALUE overrides")
        p_sync.add_argument("--allow-missing", action="store_true", help="Proceed even if some required keys missing")
        p_sync.add_argument("--dry-run", action="store_true", help="Only print what would be synced")
        p_sync.set_defaults(func=cmd_sync_secrets)

    def handle(self, *args, **options):
        return options["func"](argparse.Namespace(**options))
