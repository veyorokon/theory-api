from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict


from .base_http_adapter import BaseHTTPAdapter, InvokeOptions, InvokeResult, _error_envelope

# --- Logging -----------------------------------------------------------------
try:
    from libs.runtime_common.logging import info, warn, error, debug  # type: ignore
except Exception:  # pragma: no cover
    import logging

    _L = logging.getLogger("adapters.modal")
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    def info(event: str, **fields):
        _L.info(json.dumps({"event": event, **fields}))

    def warn(event: str, **fields):
        _L.warning(json.dumps({"event": event, **fields}))

    def error(event: str, **fields):
        _L.error(json.dumps({"event": event, **fields}))

    def debug(event: str, **fields):
        _L.debug(json.dumps({"event": event, **fields}))


# --- Options -----------------------------------------------------------------
@dataclass(frozen=True)
class ModalInvokeOptions(InvokeOptions):
    app_name: str | None = None
    function_name: str = "fastapi_app"  # matches @modal.asgi_app() name or function export
    build: bool = False  # ignored by modal adapter; for signature parity with local


# --- Use canonical naming from management commands ----
def _derive_app_name(ref: str, env: str | None, branch: str | None, user: str | None) -> str:
    from apps.core.management.commands._modal_common import modal_app_name

    # Use the canonical naming function
    env = env or "staging"  # default to staging if no env
    if env == "dev":
        return modal_app_name(ref, env=env, branch=branch, user=user)
    else:
        return modal_app_name(ref, env=env)


# --- Adapter -----------------------------------------------------------------
class ModalHTTPAdapter:
    def __init__(self, http: BaseHTTPAdapter | None = None) -> None:
        self._http = http or BaseHTTPAdapter()

    def _get_modal_web_url(self, app_name: str, function_name: str, *, env: str | None) -> str:
        # Import here to keep module import cheap in non-modal environments
        try:
            import modal  # type: ignore
        except Exception as e:  # pragma: no cover
            raise RuntimeError(f"Modal SDK import failed: {e}") from e

        try:
            # Use Function.from_name to access deployed function directly
            fn = modal.Function.from_name(app_name, function_name)
            # Use get_web_url() method (web_url property is deprecated)
            url = fn.get_web_url() if hasattr(fn, "get_web_url") else fn.web_url  # type: ignore[attr-defined]
        except Exception as e:
            error("adapter.modal.lookup.fail", app=app_name, env=env or "", fn=function_name, err=str(e))
            raise
        if not url:
            raise RuntimeError(f"Modal function has no web_url: {app_name}:{function_name}")
        info("adapter.modal.url.resolve", app=app_name, env=env or "", fn=function_name, url=url)
        return url

    def invoke_by_ref(self, *, ref: str, payload: Dict[str, Any], **options) -> InvokeResult:
        modal_opts = ModalInvokeOptions(**options)
        return self.invoke(ref=ref, payload=payload, options=modal_opts)

    def invoke(self, *, ref: str, payload: Dict[str, Any], options: ModalInvokeOptions) -> InvokeResult:
        app_name = options.app_name or _derive_app_name(ref, options.env, options.branch, options.user)
        try:
            url = self._get_modal_web_url(app_name, options.function_name, env=options.env)
        except Exception as e:
            env = _error_envelope(
                payload.get("execution_id", ""), "ERR_ENDPOINT_MISSING", f"Modal URL resolution failed: {e}"
            )
            return InvokeResult(status="error", envelope=env, http_status=0, url="")

        # Hit /run; supply-chain drift check handled by BaseHTTPAdapter
        result = self._http.invoke(
            url=url,
            payload=payload,
            options=InvokeOptions(
                expected_oci=options.expected_oci,
                timeout_s=options.timeout_s,
                run_path=options.run_path,
                health_path=options.health_path,
            ),
        )
        return result
