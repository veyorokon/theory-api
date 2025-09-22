"""
Pure Python helper functions for Modal CLI operations.

All Modal API touchpoints centralized here. No Django ORM dependencies.
"""

from __future__ import annotations
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, Any, List, Set, Tuple
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FTimeout

import yaml


# Removed old resolve_app_name function - now handled by management commands
# using apps.core.management.commands._modal_common.compute_modal_context()


def validate_env(env: str) -> None:
    """Validate environment is allowed."""
    if env not in ("dev", "staging", "main"):
        raise ValueError(f"Invalid environment '{env}'. Allowed: dev, staging, main")


def ensure_modal_auth() -> None:
    """Ensure Modal credentials are available."""
    try:
        subprocess.run(["modal", "whoami"], capture_output=True, check=True)
        return
    except Exception:
        pass

    token_id = os.getenv("MODAL_TOKEN_ID")
    token_secret = os.getenv("MODAL_TOKEN_SECRET")
    if token_id and token_secret:
        subprocess.run(
            ["modal", "token", "set", "--token-id", token_id, "--token-secret", token_secret],
            capture_output=True,
            check=True,
        )
        return

    raise RuntimeError(
        "Modal authentication is not configured. Run `modal token set` locally or set MODAL_TOKEN_ID/MODAL_TOKEN_SECRET."
    )


def _load_processor_spec(ref: str) -> Tuple[str, List[str]]:
    """Resolve processor image digest and required secrets from registry for the given ref."""
    registry_dir = Path(__file__).parent / "registry" / "processors"
    if not registry_dir.exists():
        raise RuntimeError("Processor registry not found")

    for yaml_file in registry_dir.glob("*.yaml"):
        try:
            spec = yaml.safe_load(yaml_file.read_text())
        except Exception:
            continue

        if spec.get("ref") == ref:
            image_oci = (spec.get("image") or {}).get("oci")
            if not image_oci:
                raise RuntimeError(f"Registry entry for {ref} is missing image.oci")
            secrets_spec = spec.get("secrets") or {}
            required = list(secrets_spec.get("required", []))
            return image_oci, required

    raise RuntimeError(f"Processor ref not found in registry: {ref}")


def find_required_secrets_from_registry() -> Set[str]:
    """
    Scan registry YAML files to find all required secret names.

    Returns:
        Set of secret names required across all processors
    """
    secrets = set()
    registry_dir = Path(__file__).parent / "registry" / "processors"

    if not registry_dir.exists():
        return secrets

    for yaml_file in registry_dir.glob("*.yaml"):
        try:
            with open(yaml_file) as f:
                spec = yaml.safe_load(f)

            secrets_spec = spec.get("secrets", {})
            required = secrets_spec.get("required", [])
            optional = secrets_spec.get("optional", [])

            secrets.update(required + optional)
        except Exception:
            # Skip malformed YAML files
            continue

    return secrets


def deploy(
    env: str,
    app_name: str,
    from_path: str,
    timeout: int = 900,
    *,
    processor_ref: str,
) -> Dict[str, Any]:
    """
    Deploy Modal functions to environment.

    Args:
        env: Target environment
        app_name: Modal app name
        from_path: Path to modal_app.py
        timeout: Deployment timeout in seconds

    Returns:
        Canonical result envelope
    """
    validate_env(env)
    ensure_modal_auth()

    module_path = Path(from_path)
    if not module_path.exists():
        return {"status": "error", "error": {"code": "FILE_NOT_FOUND", "message": f"Modal app not found: {from_path}"}}

    # Use module name without .py extension
    module_name = module_path.stem

    try:
        image_oci, required_secrets = _load_processor_spec(processor_ref)
        env_exports = {
            **os.environ,
            "MODAL_ENVIRONMENT": env,
            "PROCESSOR_REF": processor_ref,
            "IMAGE_REF": image_oci,
            "TOOL_SECRETS": ",".join(required_secrets),
            "MODAL_APP_NAME": app_name,
        }
        cmd = ["modal", "deploy", "--env", env, "-m", module_name]

        result = subprocess.run(
            cmd,
            cwd=str(module_path.parent),
            env=env_exports,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True,
        )

        return {
            "status": "success",
            "app_name": app_name,
            "env": env,
            "deployment": {"stdout": result.stdout, "stderr": result.stderr},
        }

    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "error": {"code": "DEPLOY_TIMEOUT", "message": f"Deployment timed out after {timeout}s"},
        }
    except subprocess.CalledProcessError as e:
        return {"status": "error", "error": {"code": "DEPLOY_FAILED", "message": f"Deploy failed: {e.stderr}"}}


def ensure_secrets(env: str, secrets_dict: Dict[str, str]) -> Dict[str, Any]:
    """
    Idempotently ensure secrets exist in Modal environment.

    Args:
        env: Target environment
        secrets_dict: Dict of {secret_name: secret_value}

    Returns:
        Summary of secret operations
    """
    validate_env(env)
    ensure_modal_auth()

    results = {"created": [], "updated": [], "unchanged": [], "errors": []}

    for name, value in secrets_dict.items():
        if not value:
            results["errors"].append(f"Empty value for secret '{name}'")
            continue

        try:
            # Use modal secret create with --force to update if exists
            cmd = ["modal", "secret", "create", name, f"{name}={value}", "--env", env, "--force"]

            result = subprocess.run(cmd, capture_output=True, text=True, check=True)

            # Modal doesn't clearly indicate create vs update, so we'll mark as updated
            results["updated"].append({"name": name, "length": len(value)})

        except subprocess.CalledProcessError as e:
            results["errors"].append(f"Failed to sync secret '{name}': {e.stderr}")

    return {"status": "success" if not results["errors"] else "partial", "env": env, "secrets": results}


def call(env: str, app_name: str, fn_name: str, payload: Dict[str, Any], timeout: int = 30) -> Dict[str, Any]:
    """
    Call a Modal function with payload using SDK.

    Args:
        env: Target environment
        app_name: Modal app name
        fn_name: Function name (run, smoke, etc.)
        payload: JSON payload to send
        timeout: Call timeout in seconds

    Returns:
        Function response or error
    """
    validate_env(env)
    ensure_modal_auth()

    try:
        import modal
        import time

        print(f"🔍 Looking up Modal function: {app_name}.{fn_name} in {env}", file=sys.stderr)

        # Use Modal SDK to invoke deployed function
        fn = modal.Function.from_name(app_name, fn_name, environment_name=env)

        print(f"📞 Calling Modal function with payload size: {len(str(payload))} chars", file=sys.stderr)
        t0 = time.time()

        # Use thread-based timeout for synchronous call
        with ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(fn.remote, payload)
            try:
                result = fut.result(timeout=timeout)
                dur = int((time.time() - t0) * 1000)

                print(f"✅ Modal call completed in {dur}ms", file=sys.stderr)

                # Modal functions should return dict (canonical envelope)
                if isinstance(result, bytes):
                    response_text = result.decode("utf-8")
                    try:
                        envelope = json.loads(response_text)
                        if isinstance(envelope, dict):
                            return envelope
                    except json.JSONDecodeError:
                        pass
                elif isinstance(result, dict):
                    return result
                else:
                    response_text = str(result)

                return {
                    "status": "success",
                    "app_name": app_name,
                    "function": fn_name,
                    "response": response_text,
                    "stderr": "",
                }
            except FTimeout:
                print(f"⏰ Modal call timed out after {timeout}s", file=sys.stderr)
                return {
                    "status": "error",
                    "error": {"code": "ERR_TIMEOUT", "message": f"Function call timed out after {timeout}s"},
                }

    except Exception as e:
        print(f"❌ Modal call failed: {type(e).__name__}: {e}", file=sys.stderr)
        if "not found" in str(e).lower():
            return {
                "status": "error",
                "error": {
                    "code": "ERR_MODAL_LOOKUP",
                    "message": f"Modal function not found: {app_name}.{fn_name} ({env})",
                },
            }
        return {
            "status": "error",
            "error": {"code": "ERR_MODAL_INVOCATION", "message": f"Function call failed: {type(e).__name__}: {e}"},
        }


def list_apps(env: str, prefix: str | None = None) -> Dict[str, Any]:
    """
    List Modal apps in environment.

    Args:
        env: Target environment
        prefix: Optional name prefix filter

    Returns:
        List of apps with metadata
    """
    validate_env(env)
    ensure_modal_auth()

    try:
        cmd = ["modal", "app", "list", "--env", env, "--json"]

        result = subprocess.run(cmd, capture_output=True, text=True, check=True)

        apps = json.loads(result.stdout) if result.stdout.strip() else []

        if prefix:
            apps = [app for app in apps if app.get("Description", "").startswith(prefix)]

        return {"status": "success", "env": env, "apps": apps, "count": len(apps)}

    except subprocess.CalledProcessError as e:
        return {"status": "error", "error": {"code": "LIST_FAILED", "message": f"Failed to list apps: {e.stderr}"}}
    except json.JSONDecodeError as e:
        return {"status": "error", "error": {"code": "PARSE_FAILED", "message": f"Failed to parse app list: {e}"}}


def tail_logs(env: str, app_name: str, fn_name: str, since_min: int = 30, limit: int = 200) -> Dict[str, Any]:
    """
    Tail recent logs for a Modal app.

    Args:
        env: Target environment
        app_name: Modal app name
        fn_name: Function name (used for filtering)
        since_min: Minutes of history to fetch (approximate)
        limit: Max number of log lines

    Returns:
        Log lines and metadata
    """
    validate_env(env)
    ensure_modal_auth()

    try:
        cmd = [
            "modal",
            "app",
            "logs",
            app_name,
            "--env",
            env,
            "--timestamps",
        ]

        # Run with longer timeout since modal app logs streams continuously
        # Need enough time to capture both historical and any new logs
        timeout_seconds = min(30, max(15, since_min))  # At least 15s, up to requested time

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_seconds)

        # Process the output
        lines = result.stdout.splitlines() if result.stdout else []

        # Always include error/crash logs regardless of function filter
        error_keywords = ["error", "failed", "runner", "usage:", "traceback", "exception", "crash"]

        if fn_name and fn_name.strip():
            # Include function-specific logs AND any error logs
            filtered_lines = [
                line for line in lines if fn_name in line or any(keyword in line.lower() for keyword in error_keywords)
            ]
        else:
            # No function filter - return all logs
            filtered_lines = lines

        # Apply limit
        if limit and len(filtered_lines) > limit:
            filtered_lines = filtered_lines[-limit:]  # Get most recent lines

        return {
            "status": "success",
            "app_name": app_name,
            "function": fn_name,
            "logs": filtered_lines,
            "stderr": result.stderr,
            "total_lines": len(lines),
            "filtered_lines": len(filtered_lines),
        }

    except subprocess.TimeoutExpired as e:
        # Timeout is expected for streaming logs - capture any partial output
        partial_output = e.stdout.decode() if e.stdout else ""
        partial_lines = partial_output.splitlines() if partial_output else []

        # Apply same filtering to partial output
        error_keywords = ["error", "failed", "runner", "usage:", "traceback", "exception", "crash"]
        if fn_name and fn_name.strip():
            filtered_partial = [
                line
                for line in partial_lines
                if fn_name in line or any(keyword in line.lower() for keyword in error_keywords)
            ]
        else:
            filtered_partial = partial_lines

        if limit and len(filtered_partial) > limit:
            filtered_partial = filtered_partial[-limit:]

        return {
            "status": "success",
            "app_name": app_name,
            "function": fn_name,
            "logs": filtered_partial,
            "stderr": "",
            "total_lines": len(partial_lines),
            "filtered_lines": len(filtered_partial),
            "message": f"Log streaming timed out after {timeout_seconds}s (captured {len(filtered_partial)} relevant lines)",
        }
    except subprocess.CalledProcessError as e:
        return {"status": "error", "error": {"code": "LOGS_FAILED", "message": f"Failed to fetch logs: {e.stderr}"}}


def delete_app(env: str, app_name: str) -> Dict[str, Any]:
    """
    Stop a Modal app (Modal's equivalent of deletion).

    Args:
        env: Target environment
        app_name: Modal app name to stop

    Returns:
        Stop result
    """
    validate_env(env)
    ensure_modal_auth()

    try:
        cmd = ["modal", "app", "stop", app_name, "--env", env]

        result = subprocess.run(cmd, capture_output=True, text=True, check=True)

        return {"status": "success", "app_name": app_name, "env": env, "deleted": True}

    except subprocess.CalledProcessError as e:
        if "not found" in e.stderr.lower() or "no such app" in e.stderr.lower():
            return {
                "status": "success",
                "app_name": app_name,
                "env": env,
                "deleted": False,
                "message": "App already stopped or not found",
            }
        return {"status": "error", "error": {"code": "STOP_FAILED", "message": f"Failed to stop app: {e.stderr}"}}
