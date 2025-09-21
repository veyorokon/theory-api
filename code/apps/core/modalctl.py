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
from typing import Dict, Any, List, Set, Tuple

import yaml


def _git_branch() -> str:
    """Get current git branch, sanitized for app names."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, check=True
        )
        return result.stdout.strip().replace("/", "-")
    except subprocess.CalledProcessError:
        return "unknown"


def resolve_app_name(env: str, processor_ref: str | None = None, preferred: str | None = None) -> str:
    """
    Determine the Modal app name for CLI operations.

    - If preferred: use exact name provided
    - If processor_ref: return canonical registry-driven name (e.g., llm-litellm-v1)
    - Else: fall back to user-branch sandbox naming

    Args:
        env: Environment (for validation only - scoping via --env flag)
        processor_ref: Optional processor reference (e.g., "llm/litellm@1")
        preferred: Optional exact name override

    Returns:
        App name for human/manual use
    """
    if preferred:
        return preferred

    user = (os.getenv("USER") or os.getenv("GITHUB_ACTOR") or "unknown").lower()
    branch = _git_branch()

    if processor_ref:
        from apps.core.adapters.modal.naming import modal_app_name_from_ref

        # Canonical naming for registry-driven deployments
        return modal_app_name_from_ref(processor_ref)

    # Generic sandbox fallback when no processor ref supplied
    return f"{user}-{branch}"


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
