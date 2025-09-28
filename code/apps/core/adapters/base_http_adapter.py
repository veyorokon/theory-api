from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Dict


import requests

# --- Logging (use project logger if available; fall back to stdlib) ----------
try:
    from libs.runtime_common.logging import info, warn, error, debug  # type: ignore
except Exception:  # pragma: no cover
    import logging

    _L = logging.getLogger("adapters.base_http")
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    def info(event: str, **fields):
        _L.info(json.dumps({"event": event, **fields}))

    def warn(event: str, **fields):
        _L.warning(json.dumps({"event": event, **fields}))

    def error(event: str, **fields):
        _L.error(json.dumps({"event": event, **fields}))

    def debug(event: str, **fields):
        _L.debug(json.dumps({"event": event, **fields}))


# --- Data structures ---------------------------------------------------------
@dataclass(frozen=True)
class InvokeResult:
    status: str
    envelope: Dict[str, Any]
    http_status: int
    url: str


@dataclass(frozen=True)
class InvokeOptions:
    expected_oci: str | None = None  # full ref or digest
    timeout_s: int = 600
    # Modal hints (optional)
    env: str | None = None
    branch: str | None = None
    user: str | None = None
    # HTTP paths
    run_path: str = "/run"
    health_path: str = "/healthz"


# --- Shared utilities --------------------------------------------------------
def _normalize_digest(ref_or_digest: str | None) -> str | None:
    """
    Return `sha256:...` if input is either `sha256:...` or `something@sha256:...`.
    Otherwise, None.
    """
    if not ref_or_digest:
        return None
    s = ref_or_digest.strip()
    if "@sha256:" in s:
        return "sha256:" + s.split("@sha256:", 1)[1]
    if s.startswith("sha256:"):
        return s
    return None


def _is_valid_envelope(env: Dict[str, Any]) -> bool:
    """
    Minimal envelope validator:
      - must include 'status' (success|error)
      - must include 'execution_id' (string)
      - on success: 'outputs' (list) and 'index_path' (string)
      - on error: 'error' dict with 'code' and 'message'
    """
    if not isinstance(env, dict):
        return False
    status = env.get("status")
    if status not in ("success", "error"):
        return False
    if not isinstance(env.get("execution_id", ""), str):
        return False
    if status == "success":
        return isinstance(env.get("outputs"), list) and isinstance(env.get("index_path", ""), str)
    if status == "error":
        err = env.get("error")
        return (
            isinstance(err, dict) and isinstance(err.get("code", ""), str) and isinstance(err.get("message", ""), str)
        )
    return False


def _error_envelope(execution_id: str, code: str, message: str, meta: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return {
        "status": "error",
        "execution_id": execution_id or "",
        "error": {"code": code, "message": message},
        "meta": meta or {},
    }


# --- Core HTTP adapter --------------------------------------------------------
class BaseHTTPAdapter:
    """
    Shared HTTP plumbing for both Local and Modal adapters.
    Responsibilities:
      - Build and POST the payload to /run (or another path).
      - Validate the returned envelope contract.
      - Normalize and verify image digest (supply-chain guard).
      - Map HTTP-level issues to canonical error envelopes.
    """

    def __init__(self, session: requests.Session | None = None) -> None:
        self._session = session or requests.Session()

    def invoke(
        self,
        *,
        url: str,
        payload: Dict[str, Any],
        options: InvokeOptions,
        headers: Dict[str, str] | None = None,
    ) -> InvokeResult:
        target = url.rstrip("/") + (options.run_path or "/run")
        headers = {"content-type": "application/json", **(headers or {})}
        start = time.monotonic()
        info("adapter.http.invoke.start", url=target, timeout_s=options.timeout_s)

        try:
            resp = self._session.post(
                target, data=json.dumps(payload).encode("utf-8"), headers=headers, timeout=options.timeout_s
            )
        except requests.exceptions.RequestException as e:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            error("adapter.http.invoke.network_error", url=target, elapsed_ms=elapsed_ms, err=str(e))
            env = _error_envelope(payload.get("execution_id", ""), "ERR_NETWORK", f"HTTP request failed: {e}")
            return InvokeResult(status="error", envelope=env, http_status=0, url=target)

        # Parse response body as JSON
        try:
            envelope = resp.json()
        except ValueError:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            error("adapter.http.invoke.invalid_json", url=target, status=resp.status_code, elapsed_ms=elapsed_ms)
            env = _error_envelope(
                payload.get("execution_id", ""), "ERR_BAD_RESPONSE", "Non-JSON response from processor"
            )
            return InvokeResult(status="error", envelope=env, http_status=resp.status_code, url=target)

        # Validate envelope shape
        if not _is_valid_envelope(envelope):
            warn(
                "adapter.http.invoke.bad_envelope",
                url=target,
                status=resp.status_code,
                envelope_preview=str(envelope)[:400],
            )
            env = _error_envelope(
                payload.get("execution_id", ""), "ERR_BAD_RESPONSE", "Invalid envelope format from processor"
            )
            return InvokeResult(status="error", envelope=env, http_status=resp.status_code, url=target)

        # Map non-2xx HTTP status to canonical error if needed
        if resp.status_code >= 400:
            # Prefer processor error if present, otherwise map generically
            if envelope.get("status") != "error":
                env = _error_envelope(
                    envelope.get("execution_id", ""), "ERR_PROCESSOR_HTTP", f"Processor HTTP {resp.status_code}"
                )
                return InvokeResult(status="error", envelope=env, http_status=resp.status_code, url=target)
            return InvokeResult(status="error", envelope=envelope, http_status=resp.status_code, url=target)

        # Supply-chain guard: digest drift check (optional)
        expected = _normalize_digest(options.expected_oci)
        actual = _normalize_digest((envelope.get("meta") or {}).get("image_digest") or "")
        if expected and actual and expected != actual:
            warn("adapter.http.invoke.digest_mismatch", expected=expected, actual=actual, url=target)
            env = _error_envelope(
                envelope.get("execution_id", ""),
                "ERR_REGISTRY_MISMATCH",
                f"Image digest {actual} != expected {expected}",
                {"expected_digest": expected, "actual_digest": actual},
            )
            return InvokeResult(status="error", envelope=env, http_status=200, url=target)

        elapsed_ms = int((time.monotonic() - start) * 1000)
        info(
            "adapter.http.invoke.settle",
            url=target,
            status=envelope.get("status"),
            http_status=resp.status_code,
            elapsed_ms=elapsed_ms,
        )
        return InvokeResult(status=envelope["status"], envelope=envelope, http_status=resp.status_code, url=target)
