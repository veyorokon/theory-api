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
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FTimeout

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


# _resolve_app_name removed - now using compute_modal_context directly for consistency


# ---------------------------
# Modal Invoker (injectable transport)
# ---------------------------


class ModalInvoker:
    """Synchronous Modal function invoker with injectable resolver for testing."""

    def __init__(self, fn_resolver):
        self._resolve = fn_resolver

    def invoke(self, app_name: str, fn_name: str, env_name: str, payload: dict, timeout_s: int) -> bytes:
        """Invoke Modal function synchronously with timeout."""
        try:
            fn = self._resolve(app_name, fn_name, env_name)
        except Exception as e:
            error("modal.lookup.fail", app_name=app_name, function=fn_name, env=env_name, error=str(e))
            raise

        # Synchronous call with thread-based timeout (no asyncio)
        with ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(fn.remote, payload)
            try:
                return fut.result(timeout=timeout_s)
            except FTimeout:
                error("modal.remote.timeout", app_name=app_name, function=fn_name, timeout_s=timeout_s)
                raise FTimeout("Modal function call timed out")


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

    def __init__(self, invoker: ModalInvoker | None = None) -> None:
        # Inject invoker for testing; default to real Modal resolver
        self._invoker = invoker or ModalInvoker(self._real_fn_resolver)

    def _real_fn_resolver(self, app_name: str, fn_name: str, env_name: str):
        """Real Modal function resolver for production use."""
        import modal  # type: ignore

        return modal.Function.from_name(app_name, fn_name, environment_name=env_name)

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

        # Resolve app name using same logic as deploy commands (single source of truth)
        from apps.core.management.commands._modal_common import compute_modal_context

        try:
            ctx = compute_modal_context(processor_ref=processor_ref)
            app_name = app_name_override or ctx.app_name
        except Exception as e:
            error("modal.naming.failed", error=str(e), processor_ref=processor_ref)
            return _err(execution_id, "ERR_CONFIG", f"Failed to resolve Modal app name: {e}", meta={"adapter": "modal"})

        # Build payload the Modal function expects
        payload = {
            "execution_id": execution_id,
            "write_prefix": write_prefix,
            "mode": mode,
            "inputs_json": inputs_json,
        }

        # Function identity and payload summary for observability
        payload_size = len(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        timeout_s = 120

        # Bind context for this modal execution
        bind(trace_id=execution_id, adapter="modal", processor_ref=processor_ref, mode=mode)

        try:
            info(
                "modal.invoke.start",
                app_name=app_name,
                function=function_name,
                timeout_s=timeout_s,
                payload_keys=sorted(payload.keys()),
                payload_size_bytes=payload_size,
                env=env_name,
            )

            # Use injected invoker for synchronous call with timeout
            try:
                raw: bytes = self._invoker.invoke(app_name, function_name, env_name, payload, timeout_s)
            except Exception as e:
                if "not found" in str(e).lower() or "lookup" in str(e).lower():
                    return _err(
                        execution_id,
                        "ERR_MODAL_LOOKUP",
                        f"Modal function not found: {app_name}.{function_name} ({env_name})",
                        meta={"adapter": "modal"},
                    )
                elif isinstance(e, FTimeout):
                    return _err(
                        execution_id,
                        "ERR_TIMEOUT",
                        "Modal function call timed out",
                        meta={"adapter": "modal"},
                    )
                else:
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

            # Strict envelope validation - adapter is transport-only
            if not isinstance(env, dict):
                error("modal.invoke.error", reason="non_dict_response", type=type(env).__name__)
                return _err(
                    execution_id,
                    "ERR_MODAL_INVOCATION",
                    "Modal function returned non-dict response",
                    meta={"adapter": "modal"},
                )

            status = env.get("status")
            if status not in ("success", "error"):
                error("modal.invoke.error", reason="invalid_status", status=status, received_keys=list(env.keys())[:5])
                return _err(
                    execution_id,
                    "ERR_MODAL_INVOCATION",
                    "Modal function returned non-canonical envelope",
                    meta={"adapter": "modal"},
                )

            # Validate execution_id presence in canonical envelopes
            if not env.get("execution_id"):
                error("modal.invoke.error", reason="missing_execution_id", status=status)
                return _err(
                    execution_id,
                    "ERR_MODAL_INVOCATION",
                    "Modal function returned envelope without execution_id",
                    meta={"adapter": "modal"},
                )

            # Log completion based on status
            if status == "success":
                info(
                    "modal.invoke.complete",
                    status="success",
                    outputs_count=len(env.get("outputs", []) or []),
                    index_path=env.get("index_path"),
                )
                return env
            else:  # status == "error"
                error_code = (env.get("error") or {}).get("code")
                error(
                    "modal.invoke.complete",
                    status="error",
                    error_code=error_code,
                    message=(env.get("error") or {}).get("message"),
                )
                return env
        finally:
            # Clear logging context to prevent leakage
            clear()
