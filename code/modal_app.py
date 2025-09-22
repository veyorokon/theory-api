# code/modal_app.py
"""Modal app entry point for processor containers (single `run` function).

This module exposes exactly one Modal function:

* ``run(payload: dict) -> bytes`` — validates the payload, executes the
  processor ``main`` module in a subprocess, and returns a canonical envelope
  (success or error) as UTF-8 JSON bytes.

Smoke or canary tests are simply invocations of ``run`` with ``mode="mock"`` or
``mode="real"`` respectively. There are no alternate Modal functions for these
test types; all execution happens through the same surface.

Environment contract (injected at deploy time):

* ``IMAGE_REF`` – required, GHCR manifest digest to use for the Modal image.
* ``PROCESSOR_REF`` – required, e.g. ``llm/litellm@1``.
* ``TOOL_SECRETS`` – optional CSV of Modal secret names to mount (consumed only
  when ``mode="real"``).
* ``MODAL_APP_NAME`` – optional override; otherwise derived from
  ``libs.runtime_common.modal_naming.modal_app_name``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any, Dict, Iterable, List, Tuple

import modal

# ---------- Constants & helpers ----------

# Provider env vars we intentionally clear before mock executions
_PROVIDER_ENV_VARS = (
    "OPENAI_API_KEY",
    "REPLICATE_API_TOKEN",
    "ANTHROPIC_API_KEY",
    "OPENROUTER_API_KEY",
)


# Minimal, dependency-free logging (single-line JSON to stderr)
def _log(event: str, **fields: Any) -> None:
    payload = {"event": event, **fields}
    try:
        print(json.dumps(payload, separators=(",", ":"), sort_keys=False), file=sys.stderr, flush=True)
    except Exception:
        # Last resort if something in fields isn't serializable
        print(json.dumps({"event": event, "msg": str(fields)}), file=sys.stderr, flush=True)


def _ok(execution_id: str, outputs: List[Dict[str, Any]], index_path: str, meta: Dict[str, Any] | None = None) -> bytes:
    env = {
        "status": "success",
        "execution_id": execution_id,
        "outputs": outputs,
        "index_path": index_path,
        "meta": meta or {},
    }
    return json.dumps(env, separators=(",", ":")).encode("utf-8")


def _err(execution_id: str | None, code: str, message: str, meta: Dict[str, Any] | None = None) -> bytes:
    env = {
        "status": "error",
        "execution_id": execution_id or "",
        "error": {"code": code, "message": message},
        "meta": meta or {},
    }
    return json.dumps(env, separators=(",", ":")).encode("utf-8")


def _require_env(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return v


def _module_path_from_ref(ref: str) -> Tuple[str, str]:
    """
    Convert 'ns/name@ver' -> ('apps.core.processors.ns_name.main', 'ns_name')
    """
    try:
        ns, rest = ref.split("/", 1)
        name, _ver = rest.split("@", 1)
    except ValueError:
        raise RuntimeError(f"Invalid PROCESSOR_REF '{ref}'. Expected 'ns/name@ver'.")

    pkg = f"{ns}_{name}".replace("-", "_")
    module = f"apps.core.processors.{pkg}.main"
    return module, pkg


def _modal_secrets_from_env(names_csv: str | None) -> List[modal.Secret]:
    secrets: List[modal.Secret] = []
    if not names_csv:
        return secrets
    for raw in names_csv.split(","):
        s = raw.strip()
        if not s:
            continue
        try:
            secrets.append(modal.Secret.from_name(s))
        except Exception as e:
            # Non-fatal: allow deploy without the secret (run() in real mode will still fail gracefully)
            _log("modal.secret.resolve.fail", secret=s, error=str(e))
    return secrets


def _app_name_from_env() -> str:
    """
    Compute Modal app name from environment variables.
    Uses shared naming utility to ensure consistency with deploy/lookup.
    """
    ref = os.environ.get("PROCESSOR_REF", "").strip()
    preferred = os.environ.get("MODAL_APP_NAME", "").strip()

    if preferred:
        return preferred

    if ref:
        try:
            from libs.runtime_common.modal_naming import modal_app_name

            env = os.environ.get("MODAL_ENVIRONMENT", "dev").strip().lower()
            if env == "dev":
                branch = os.environ.get("BRANCH_NAME", "").strip()
                user = os.environ.get("DEPLOY_USER", "").strip() or os.environ.get("USER", "").strip()
                if branch and user:
                    return modal_app_name(ref, env=env, branch=branch, user=user)
                else:
                    _log("app.naming.dev_fallback", missing_branch=not branch, missing_user=not user)
            else:
                return modal_app_name(ref, env=env)
        except Exception as e:
            _log("app.naming.error", error=str(e), ref=ref)

    # Final fallback for manual deploys or errors
    return "manual-deploy"


def _validate_payload(payload: Dict[str, Any]) -> Tuple[str, str, str, Dict[str, Any]]:
    """
    Validate incoming payload and return (execution_id, write_prefix, mode, inputs_json_dict).
    Accepts either 'inputs_json' as a dict or a JSON string.
    """
    if not isinstance(payload, dict):
        raise ValueError("Payload must be a JSON object")

    execution_id = str(payload.get("execution_id", "")).strip()
    write_prefix = str(payload.get("write_prefix", "")).strip()
    mode = str(payload.get("mode", "") or "mock").strip().lower()
    inputs_json = payload.get("inputs_json")
    inputs = payload.get("inputs")

    if not execution_id:
        raise ValueError("Missing 'execution_id'")
    if not write_prefix:
        raise ValueError("Missing 'write_prefix'")
    if mode not in ("mock", "real"):
        raise ValueError("Invalid 'mode' (allowed: 'mock','real')")

    if inputs_json is None and inputs is None:
        raise ValueError("Missing 'inputs' payload")

    if inputs is not None:
        if isinstance(inputs, dict):
            inputs_obj = dict(inputs)
        else:
            raise ValueError("'inputs' must be a JSON object if provided")
    else:
        if isinstance(inputs_json, str):
            try:
                inputs_obj = json.loads(inputs_json)
            except json.JSONDecodeError as e:
                raise ValueError(f"inputs_json is not valid JSON: {e}") from e
        elif isinstance(inputs_json, dict):
            inputs_obj = dict(inputs_json)
        else:
            raise ValueError("inputs_json must be an object or JSON string")

    # Normalize the schema/mode on the inputs itself (processors expect 'schema' and read 'mode')
    if "schema" not in inputs_obj:
        inputs_obj["schema"] = "v1"
    inputs_obj["mode"] = mode

    return execution_id, write_prefix, mode, inputs_obj


def _build_subprocess_cmd(module: str, *, inputs_path: str, write_prefix: str, execution_id: str) -> List[str]:
    """
    Invoke the processor's main module as a script:
      python -m apps.core.processors.<pkg>.main --inputs <file> --write-prefix <prefix> --execution-id <uuid>
    """
    return [
        sys.executable,
        "-m",
        module,
        "--inputs",
        inputs_path,
        "--write-prefix",
        write_prefix,
        "--execution-id",
        execution_id,
    ]


def _write_tmp_json(obj: Dict[str, Any]) -> str:
    import tempfile

    fd, path = tempfile.mkstemp(prefix="inputs-", suffix=".json")
    os.close(fd)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, separators=(",", ":"))
    return path


def _clear_provider_envs() -> None:
    for k in _PROVIDER_ENV_VARS:
        if os.environ.pop(k, None) is not None:
            _log("env.clear", var=k)


# ---------- Modal app wiring ----------

IMAGE_REF = _require_env("IMAGE_REF")
TOOL_SECRETS = os.getenv("TOOL_SECRETS", "")

image = modal.Image.from_registry(IMAGE_REF)
app = modal.App(_app_name_from_env())


@app.function(
    name="run",  # custom name => must set serialized=True
    image=image,
    serialized=True,
    secrets=_modal_secrets_from_env(TOOL_SECRETS),
    timeout=60 * 10,
)
def run(payload: Dict[str, Any] | None = None) -> bytes:
    """
    Execute processor with provided payload.
    Payload contract:
      {
        "execution_id": "<uuid>",
        "write_prefix": "/artifacts/outputs/<something>/{execution_id}/",
        "mode": "mock" | "real",
        "inputs_json": { ... } | "<json string>"
      }
    Returns a canonical envelope (success or error) as bytes.
    """
    try:
        # Defensive: treat empty/malformed payloads as no-ops (don’t crash-loop)
        if not payload:
            _log("invoke.payload.missing")
            return _err(None, "ERR_PAYLOAD", "Missing payload")

        _log("invoke.payload.received", keys=list(payload.keys()))

        ref = os.environ.get("PROCESSOR_REF", "").strip()
        if not ref:
            return _err(None, "ERR_CONFIG", "PROCESSOR_REF is not set")

        module, _pkg = _module_path_from_ref(ref)
        eid, write_prefix, mode, inputs_obj = _validate_payload(payload)

        if mode == "mock":
            _clear_provider_envs()

        # In mock mode we should not require provider secrets.
        # In real mode: provider secrets must be present (processor will enforce).
        _log(
            "processor.exec.start",
            processor_ref=ref,
            mode=mode,
            execution_id=eid,
            write_prefix=write_prefix,
        )

        inputs_path = _write_tmp_json(inputs_obj)
        cmd = _build_subprocess_cmd(module, inputs_path=inputs_path, write_prefix=write_prefix, execution_id=eid)

        # Debug instrumentation (controlled by payload flag or env var)
        def _dbg(tag, **k):
            try:
                print(json.dumps({"event": tag, **k}), file=sys.stderr, flush=True)
            except Exception:
                pass

        dbg_enabled = bool(payload.get("debug_exec") or os.environ.get("MODAL_DEBUG_EXEC"))

        # Prove module importability and environment setup
        if dbg_enabled:
            import importlib.util

            spec = importlib.util.find_spec(module)
            _dbg(
                "exec.debug.preflight",
                module=module,
                spec_found=bool(spec),
                cwd=os.getcwd(),
                sys_executable=sys.executable,
                pythonpath=os.environ.get("PYTHONPATH"),
                sys_path_head=sys.path[:3],
            )

        # Set up child environment with explicit PYTHONPATH
        from libs.runtime_common.fingerprint import build_clean_env

        child_env = build_clean_env()
        proj_root = child_env.get("PROJECT_ROOT") or "/app"  # Match container layout
        child_env["PYTHONPATH"] = f"{proj_root}/code:" + child_env.get("PYTHONPATH", "")

        if dbg_enabled:
            _dbg(
                "exec.debug.argv",
                module=module,
                cwd=proj_root,
                cmd=cmd,
                child_env_pythonpath=child_env.get("PYTHONPATH"),
                child_env_path=child_env.get("PATH", "")[:200],
            )

        # Run the processor main with timeout; log start/duration + bounded IO breadcrumbs.
        def _digest(b: bytes) -> str:
            import hashlib

            return "sha256:" + hashlib.sha256(b).hexdigest()

        def _tail(b: bytes, n: int = 256) -> str:
            try:
                return b.decode("utf-8", "replace")[-n:]
            except Exception:
                return "<non-text>"

        import time

        _log(
            "processor.exec.start",
            module=module,
            cmd=cmd,
            mode=mode,
            processor_ref=ref,
            write_prefix=write_prefix,
            execution_id=eid,
        )
        t0 = time.time()
        timeout_s = 600
        try:
            proc = subprocess.run(
                cmd,
                cwd=proj_root,
                env=child_env,
                capture_output=True,
                text=True,  # Changed to text for easier debug
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired:
            dur = int((time.time() - t0) * 1000)
            _log(
                "processor.exec.timeout",
                timeout_s=timeout_s,
                duration_ms=dur,
                module=module,
                processor_ref=ref,
                execution_id=eid,
            )
            return _err(eid, "ERR_MODAL_TIMEOUT", "Processor execution timed out")

        dur = int((time.time() - t0) * 1000)
        stderr_text = proc.stderr or ""
        stdout_text = proc.stdout or ""

        # Convert back to bytes for existing digest/tail functions
        stderr_b = stderr_text.encode("utf-8")
        stdout_b = stdout_text.encode("utf-8")
        stderr_tail = _tail(stderr_b)
        stdout_tail = _tail(stdout_b)
        stderr_len = len(stderr_b)
        stdout_len = len(stdout_b)
        stderr_sha = _digest(stderr_b) if stderr_len else None
        stdout_sha = _digest(stdout_b) if stdout_len else None

        # Post-execution debug logging
        if dbg_enabled:
            _dbg(
                "exec.debug.post",
                returncode=proc.returncode,
                stdout_preview=stdout_text[:200],
                stderr_preview=stderr_text[:200],
                duration_ms=dur,
            )

        # Non-zero exit → structured fail with bounded diagnostics.
        if proc.returncode != 0:
            _log(
                "processor.exec.fail",
                returncode=proc.returncode,
                duration_ms=dur,
                stderr_len=stderr_len,
                stderr_sha=stderr_sha,
                stderr_tail=stderr_tail,
                stdout_len=stdout_len,
                stdout_sha=stdout_sha,
                stdout_tail=stdout_tail,
                processor_ref=ref,
                execution_id=eid,
            )
            # Exit code taxonomy for better error classification
            if proc.returncode == 2 and "required" in stderr_text:
                return _err(
                    eid,
                    "ERR_ADAPTER_INVOCATION",
                    "missing_required_args",
                    meta={"stderr_tail": stderr_tail, "returncode": proc.returncode},
                )
            elif proc.returncode == 137:
                return _err(
                    eid,
                    "ERR_ADAPTER_INVOCATION",
                    "terminated_by_oomkill",
                    meta={"stderr_tail": stderr_tail, "returncode": proc.returncode},
                )
            elif proc.returncode == 143:
                return _err(
                    eid,
                    "ERR_ADAPTER_INVOCATION",
                    "terminated_by_sigterm",
                    meta={"stderr_tail": stderr_tail, "returncode": proc.returncode},
                )
            else:
                return _err(
                    eid,
                    "ERR_ADAPTER_INVOCATION",
                    f"subprocess_failed_rc_{proc.returncode}",
                    meta={"stderr_tail": stderr_tail, "returncode": proc.returncode},
                )

        # Parse stdout as canonical envelope; log invalid JSON with breadcrumbs.
        try:
            envelope = json.loads(stdout_b.decode("utf-8", "replace"))
        except Exception as ex:
            _log(
                "processor.exec.envelope_invalid",
                error=str(ex),
                duration_ms=dur,
                stdout_len=stdout_len,
                stdout_sha=stdout_sha,
                stdout_tail=stdout_tail,
                processor_ref=ref,
                execution_id=eid,
            )
            return _err(eid, "ERR_ADAPTER_INVOCATION", "Processor emitted invalid JSON")

        _log(
            "processor.exec.success",
            duration_ms=dur,
            outputs_count=len(envelope.get("outputs", [])),
            processor_ref=ref,
            execution_id=eid,
        )
        return json.dumps(envelope, separators=(",", ":")).encode("utf-8")

    except ValueError as ve:
        _log("invoke.payload.invalid", error=str(ve))
        return _err(None, "ERR_PAYLOAD", str(ve))
    except Exception as e:
        _log("invoke.unhandled", error=str(e))
        return _err(None, "ERR_APP", f"{type(e).__name__}: {e}")
