"""
Pure Python helper functions for Modal CLI operations.

All Modal API touchpoints centralized here. No Django ORM dependencies.
"""

from __future__ import annotations
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Dict, Any, List, Set

import yaml


def resolve_app_name(env: str, preferred: str | None = None) -> str:
    """
    Resolve Modal app name following naming conventions.

    Args:
        env: Environment (dev|staging|main)
        preferred: Optional preferred name override

    Returns:
        Canonical app name following conventions
    """
    if preferred:
        return preferred

    if env in ("staging", "main"):
        return f"theory-{env}"

    # dev environment: theory-dev-{user}-{branch}
    user = os.getenv("USER", "unknown").lower()
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, check=True
        )
        branch = result.stdout.strip().replace("/", "-")
    except subprocess.CalledProcessError:
        branch = "unknown"

    return f"theory-dev-{user}-{branch}"


def validate_env(env: str) -> None:
    """Validate environment is allowed."""
    if env not in ("dev", "staging", "main"):
        raise ValueError(f"Invalid environment '{env}'. Allowed: dev, staging, main")


def ensure_modal_auth() -> None:
    """Ensure Modal credentials are available."""
    if not os.getenv("MODAL_TOKEN_ID") or not os.getenv("MODAL_TOKEN_SECRET"):
        raise RuntimeError("MODAL_TOKEN_ID and MODAL_TOKEN_SECRET must be set")


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


def deploy(env: str, app_name: str, from_path: str, timeout: int = 900) -> Dict[str, Any]:
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
        cmd = ["modal", "deploy", "--env", env, "-m", module_name]

        result = subprocess.run(
            cmd,
            cwd=str(module_path.parent),
            env={**os.environ, "MODAL_ENVIRONMENT": env},
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


def call(env: str, app_name: str, fn_name: str, payload: Dict[str, Any], timeout: int = 900) -> Dict[str, Any]:
    """
    Call a Modal function with payload.

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
        # Create temporary file for payload
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(payload, f)
            payload_file = f.name

        try:
            cmd = ["modal", "run", "--env", env, f"{app_name}::{fn_name}", "--from-file", payload_file]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=True)

            return {
                "status": "success",
                "app_name": app_name,
                "function": fn_name,
                "response": result.stdout,
                "stderr": result.stderr,
            }

        finally:
            os.unlink(payload_file)

    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "error": {"code": "CALL_TIMEOUT", "message": f"Function call timed out after {timeout}s"},
        }
    except subprocess.CalledProcessError as e:
        return {"status": "error", "error": {"code": "CALL_FAILED", "message": f"Function call failed: {e.stderr}"}}


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
            apps = [app for app in apps if app.get("name", "").startswith(prefix)]

        return {"status": "success", "env": env, "apps": apps, "count": len(apps)}

    except subprocess.CalledProcessError as e:
        return {"status": "error", "error": {"code": "LIST_FAILED", "message": f"Failed to list apps: {e.stderr}"}}
    except json.JSONDecodeError as e:
        return {"status": "error", "error": {"code": "PARSE_FAILED", "message": f"Failed to parse app list: {e}"}}


def tail_logs(env: str, app_name: str, fn_name: str, since_min: int = 30, limit: int = 200) -> Dict[str, Any]:
    """
    Tail recent logs for a Modal function.

    Args:
        env: Target environment
        app_name: Modal app name
        fn_name: Function name
        since_min: Minutes of history to fetch
        limit: Max number of log lines

    Returns:
        Log lines and metadata
    """
    validate_env(env)
    ensure_modal_auth()

    try:
        cmd = [
            "modal",
            "logs",
            "--env",
            env,
            f"{app_name}::{fn_name}",
            "--since",
            f"{since_min}m",
            "--lines",
            str(limit),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, check=True)

        return {
            "status": "success",
            "app_name": app_name,
            "function": fn_name,
            "logs": result.stdout.splitlines(),
            "stderr": result.stderr,
        }

    except subprocess.CalledProcessError as e:
        return {"status": "error", "error": {"code": "LOGS_FAILED", "message": f"Failed to fetch logs: {e.stderr}"}}


def delete_app(env: str, app_name: str) -> Dict[str, Any]:
    """
    Delete a Modal app.

    Args:
        env: Target environment
        app_name: Modal app name to delete

    Returns:
        Deletion result
    """
    validate_env(env)
    ensure_modal_auth()

    try:
        cmd = ["modal", "app", "delete", app_name, "--env", env, "--yes"]

        result = subprocess.run(cmd, capture_output=True, text=True, check=True)

        return {"status": "success", "app_name": app_name, "env": env, "deleted": True}

    except subprocess.CalledProcessError as e:
        if "not found" in e.stderr.lower():
            return {
                "status": "success",
                "app_name": app_name,
                "env": env,
                "deleted": False,
                "message": "App already deleted",
            }
        return {"status": "error", "error": {"code": "DELETE_FAILED", "message": f"Failed to delete app: {e.stderr}"}}
