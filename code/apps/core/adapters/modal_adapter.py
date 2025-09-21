# code/apps/core/adapters/modal_adapter.py
"""
ModalAdapter: thin, explicit orchestrator for remote processor execution on Modal.

Design goals:
- Keyword-only public surface: invoke(*, ...)
- Single responsibility: call the deployed Modal function with a validated payload
- Return canonical envelopes (success/error); never leak stack traces upstream
- Respect two-mode system: mode ∈ {"mock", "real"}; adapter never reinterprets mode
- Naming: resolve app name from PROCESSOR_REF or override; CI vs. human consistency
- Minimal dependency footprint: if modal is missing or lookup fails, return error envelope

Expected deployed Modal functions (see code/modal_app.py):
- app.function(name="run",    serialized=True): accepts payload dict and returns canonical envelope (bytes)
- app.function(name="smoke",  serialized=True): optional; forced mock, used by CI post-deploy smoke step
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from django.conf import settings

# Import shared logging infrastructure
from apps.core.logging import bind, clear, info, error


# ---------------------------
# Canonical envelopes
# ---------------------------


def _ok(
    execution_id: str, outputs: List[Dict[str, Any]], index_path: str, meta: Dict[str, Any] | None = None
) -> Dict[str, Any]:
    return {
        "status": "success",
        "execution_id": execution_id,
        "outputs": outputs,
        "index_path": index_path,
        "meta": meta or {},
    }


def _err(execution_id: str, code: str, message: str, meta: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return {
        "status": "error",
        "execution_id": execution_id,
        "error": {"code": code, "message": message},
        "meta": meta or {},
    }


# ---------------------------
# App name resolution
# ---------------------------


def _canonical_app_name_from_ref(ref: str) -> str:
    """
    Convert 'ns/name@ver' -> 'ns-name-v<ver>' with dashes.
    Fallback used when the shared naming helper is unavailable.
    """
    try:
        ns, rest = ref.split("/", 1)
        name, ver = rest.split("@", 1)
        slug = f"{ns}-{name}".replace("_", "-")
        return f"{slug}-v{ver}"
    except Exception:
        return "manual-deploy"


def _resolve_app_name(*, processor_ref: str, preferred: str | None) -> str:
    """
    Ordering:
      1) explicit preferred app name (e.g., via CLI/ENV)
      2) shared helper from adapters.modal.naming (if importable)
      3) local canonical derivation
    """
    if preferred:
        return preferred
    try:
        from apps.core.adapters.modal.naming import modal_app_name_from_ref  # type: ignore

        return modal_app_name_from_ref(processor_ref)
    except Exception:
        return _canonical_app_name_from_ref(processor_ref)


# ---------------------------
# Adapter
# ---------------------------


class ModalAdapter:
    """
    Thin client that invokes Modal functions remotely and relays canonical envelopes.

    Public API:
        invoke(
            *,
            processor_ref: str,
            execution_id: str,
            write_prefix: str,
            mode: str,                      # "mock" | "real"
            inputs: Mapping[str, Any] | None = None,
            config: Optional[ModalAdapterConfig] = None,
        ) -> Dict[str, Any]                # canonical envelope
    """

    def __init__(self) -> None:
        # Lazy import of modal in invoke() for better testability environments
        pass

    def invoke(
        self,
        *,
        processor_ref: str,
        mode: str,
        inputs_json: Dict[str, Any],
        write_prefix: str,
        execution_id: str,
        registry_snapshot: Dict[str, Any],
        adapter_opts: Dict[str, Any],
        secrets_present: List[str],
    ) -> Dict[str, Any]:
        """
        Invoke processor using the deployed Modal function and return canonical envelope.

        This follows the same contract as LocalAdapter but uses pre-deployed Modal functions
        for execution instead of local containers.
        """
        # Validate minimal arguments early
        if not processor_ref:
            return _err(execution_id, "ERR_CONFIG", "Missing processor_ref", meta={"adapter": "modal"})
        if not execution_id:
            return _err(execution_id, "ERR_CONFIG", "Missing execution_id", meta={"adapter": "modal"})
        if not write_prefix:
            return _err(execution_id, "ERR_CONFIG", "Missing write_prefix", meta={"adapter": "modal"})

        # Extract processor spec from registry snapshot
        try:
            spec = registry_snapshot["processors"][processor_ref]
        except KeyError:
            return _err(
                execution_id,
                "ERR_CONFIG",
                f"Processor {processor_ref} not found in registry",
                meta={"adapter": "modal"},
            )

        # Extract secrets definition
        secrets_spec = spec.get("secrets", {}) or {}
        if isinstance(secrets_spec, dict):
            required_secrets = list(secrets_spec.get("required", []))
            optional_secrets = list(secrets_spec.get("optional", []))
        elif isinstance(secrets_spec, list):
            required_secrets = list(secrets_spec)
            optional_secrets = []
        else:
            required_secrets = []
            optional_secrets = []

        # Validate required secrets are present (names only) - skip in mock mode for hermetic PR lane
        if mode == "real":
            missing = [name for name in required_secrets if name not in secrets_present]
            if missing:
                return _err(
                    execution_id,
                    "ERR_MISSING_SECRET",
                    "Required secret(s) missing: " + ", ".join(missing),
                    meta={"adapter": "modal"},
                )

        # Resolve Modal environment / function configuration
        env_from_settings = getattr(settings, "MODAL_ENVIRONMENT", None)
        env_from_env = os.getenv("MODAL_ENVIRONMENT")
        env_name = adapter_opts.get("env_name") or env_from_settings or env_from_env or "dev"
        function_name = adapter_opts.get("function", "run")
        app_name_override = adapter_opts.get("app_name_override")

        # Resolve app name
        app_name = _resolve_app_name(processor_ref=processor_ref, preferred=app_name_override)

        # Build payload the Modal function expects
        payload = {
            "execution_id": execution_id,
            "write_prefix": write_prefix,
            "mode": mode,
            "inputs_json": inputs_json,
        }

        # Bind context for this modal execution
        bind(trace_id=execution_id, adapter="modal", processor_ref=processor_ref, mode=mode)

        try:
            info(
                "modal.invoke",
                app=app_name,
                fn=function_name,
                env=env_name,
                keys=list(payload.keys()),
            )

            # Import modal only now; return helpful error if unavailable
            try:
                import modal  # type: ignore
            except Exception as e:
                error("modal.import.fail", error=str(e))
                return _err(execution_id, "ERR_DEPENDENCY", "Modal SDK not installed", meta={"adapter": "modal"})

            # Lookup remote function and call it
            try:
                fn = modal.Function.lookup(app_name, function_name, environment_name=env_name)
            except Exception as e:
                error("modal.lookup.fail", app=app_name, fn=function_name, env=env_name, error=str(e))
                return _err(
                    execution_id,
                    "ERR_MODAL_LOOKUP",
                    f"Modal function not found: {app_name}.{function_name} ({env_name})",
                    meta={"adapter": "modal"},
                )

            try:
                # Remote call returns bytes (canonical envelope JSON) per modal_app.py contract
                raw: bytes = fn.remote(payload)  # type: ignore[attr-defined]
            except Exception as e:
                error("modal.remote.fail", app=app_name, fn=function_name, env=env_name, error=str(e))
                return _err(
                    execution_id,
                    "ERR_MODAL_INVOCATION",
                    f"Modal invocation failed: {type(e).__name__}: {e}",
                    meta={"adapter": "modal"},
                )

            # Decode + parse envelope
            try:
                txt = raw.decode("utf-8", errors="replace").strip()
                env = json.loads(txt) if txt else {}
            except Exception as e:
                error("modal.decode.fail", error=str(e))
                return _err(
                    execution_id,
                    "ERR_MODAL_PAYLOAD",
                    "Failed to decode/parse response from Modal function",
                    meta={"adapter": "modal"},
                )

            # Validate envelope shape minimally
            status = env.get("status")
            if status == "success":
                info(
                    "modal.complete",
                    status="success",
                    outputs_count=len(env.get("outputs", []) or []),
                    index_path=env.get("index_path"),
                )
                return env
            elif status == "error":
                error(
                    "modal.complete",
                    status="error",
                    code=(env.get("error") or {}).get("code"),
                    message=(env.get("error") or {}).get("message"),
                )
                return env
            else:
                # If backend returned something unexpected, wrap it
                error("modal.complete.unexpected", received_keys=list(env.keys()))
                return _err(
                    execution_id,
                    "ERR_MODAL_PAYLOAD",
                    "Modal function returned an unexpected payload",
                    meta={"adapter": "modal"},
                )
        finally:
            # Clear logging context to prevent leakage
            clear()
