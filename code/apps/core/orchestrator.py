from __future__ import annotations

import json
import sys
import uuid
import traceback
from dataclasses import dataclass
from typing import Any, Dict, Protocol


# --- Logging -----------------------------------------------------------------
try:
    from libs.runtime_common.logging import info, warn, error, debug  # type: ignore
except Exception:  # pragma: no cover

    def _log(level: str, event: str, **fields: Any) -> None:
        base = {"level": level, "event": event, "service": "orchestrator"}
        base.update(fields)
        sys.stderr.write(json.dumps(base, separators=(",", ":"), sort_keys=False) + "\n")
        sys.stderr.flush()

    def info(event: str, **fields: Any) -> None:
        _log("info", event, **fields)

    def warn(event: str, **fields: Any) -> None:
        _log("warn", event, **fields)

    def error(event: str, **fields: Any) -> None:
        _log("error", event, **fields)

    def debug(event: str, **fields: Any) -> None:
        _log("debug", event, **fields)


# --- Result / Protocol --------------------------------------------------------
@dataclass
class InvokeResult:
    status: str
    envelope: Dict[str, Any]
    http_status: int
    url: str
    stderr_tail: str | None = None


class TransportAdapter(Protocol):
    def invoke_by_ref(
        self, *, ref: str, payload: Dict[str, Any], timeout_s: int = 600, expected_oci: str | None = None, **kwargs: Any
    ) -> InvokeResult: ...


# --- Adapter selection --------------------------------------------------------
def _get_adapter(adapter_name: str) -> TransportAdapter:
    name = (adapter_name or "").strip().lower()
    if name == "local":
        from apps.core.adapters.local_adapter import LocalHTTPAdapter  # type: ignore

        return LocalHTTPAdapter()
    if name == "modal":
        from apps.core.adapters.modal_adapter import ModalHTTPAdapter  # type: ignore

        return ModalHTTPAdapter()
    raise ValueError(f"Unknown adapter '{adapter_name}'. Expected one of: local, modal.")


# --- Utilities ----------------------------------------------------------------
def _normalize_digest(oci_or_digest: str | None) -> str | None:
    if not oci_or_digest:
        return None
    s = oci_or_digest.strip()
    if "@sha256:" in s:
        return "sha256:" + s.split("@sha256:", 1)[1]
    if s.startswith("sha256:"):
        return s
    return None


def _require_execution_id(execution_id: str | None) -> str:
    eid = (execution_id or "").strip()
    return eid or str(uuid.uuid4())


def _validate_write_prefix(write_prefix: str | None, require_placeholder: bool = True) -> str:
    wp = (write_prefix or "").strip()
    if require_placeholder and "{execution_id}" not in wp:
        raise ValueError("--write-prefix must include '{execution_id}' to prevent output collisions")
    return wp


# --- Options ------------------------------------------------------------------
@dataclass
class ExecutionOptions:
    adapter: str
    ref: str
    mode: str = "mock"
    inputs: Dict[str, Any] | None = None
    write_prefix: str | None = None
    expected_oci: str | None = None
    timeout_s: int = 600
    require_prefix_placeholder: bool = True
    extra: Dict[str, Any] | None = None
    build: bool = False
    # Modal hints (optional)
    env: str | None = None
    branch: str | None = None
    user: str | None = None


# --- Orchestrator -------------------------------------------------------------
class Orchestrator:
    """
    Transport-only orchestrator:
      1) Build canonical payload
      2) Call adapter.invoke_by_ref(...)
      3) Validate / unwrap result
      4) Return canonical envelope (dict)
    """

    def __init__(self) -> None:
        pass

    def execute(self, opts: ExecutionOptions) -> Dict[str, Any]:
        ref = (opts.ref or "").strip()
        if "/" not in ref or "@" not in ref:
            raise ValueError(f"Invalid ref '{ref}'. Expected 'ns/name@ver'.")

        eid = _require_execution_id((opts.extra or {}).get("execution_id") if opts.extra else None)
        write_prefix = _validate_write_prefix(opts.write_prefix, opts.require_prefix_placeholder)
        expected_digest = _normalize_digest(opts.expected_oci)

        payload: Dict[str, Any] = {
            "schema": "v1",
            "execution_id": eid,
            "ref": ref,
            "mode": (opts.mode or "mock").strip(),
            "inputs": opts.inputs or {},
            "write_prefix": write_prefix,
        }

        info(
            "execution.start", adapter=opts.adapter, processor_ref=ref, mode=payload["mode"], write_prefix=write_prefix
        )

        adapter = _get_adapter(opts.adapter)
        try:
            result: InvokeResult = adapter.invoke_by_ref(
                ref=ref,
                payload=payload,
                timeout_s=opts.timeout_s,
                expected_oci=expected_digest,
                build=opts.build,
                env=opts.env,
                branch=opts.branch,
                user=opts.user,
            )
        except Exception as ex:
            tb = traceback.format_exc(limit=2)
            error("adapter.invoke.error", adapter=opts.adapter, ref=ref, exc=str(ex), tb=tb)
            return {
                "status": "error",
                "execution_id": eid,
                "error": {"code": "ERR_ADAPTER", "message": f"Adapter failure: {ex.__class__.__name__}"},
                "meta": {"adapter": opts.adapter},
            }

        env = result.envelope or {}
        status = str(env.get("status", "")).lower()
        got_eid = str(env.get("execution_id", "")).strip()

        if got_eid and got_eid != eid:
            warn(
                "execution.envelope.execution_id_mismatch",
                expected=eid,
                got=got_eid,
                url=result.url,
                http_status=result.http_status,
            )

        if status not in ("success", "error"):
            warn(
                "execution.envelope.unknown_status",
                status=status or "<missing>",
                url=result.url,
                http_status=result.http_status,
            )

        info("execution.settle", status=status or "<missing>", http_status=result.http_status, url=result.url)
        return env


# --- Convenience --------------------------------------------------------------
def run(
    *,
    adapter: str,
    ref: str,
    mode: str,
    inputs: Dict[str, Any],
    write_prefix: str,
    expected_oci: str | None,
    timeout_s: int = 600,
    require_prefix_placeholder: bool = True,
    extra: Dict[str, Any] | None = None,
    build: bool = False,
    env: str | None = None,
    branch: str | None = None,
    user: str | None = None,
) -> Dict[str, Any]:
    orch = Orchestrator()
    opts = ExecutionOptions(
        adapter=adapter,
        ref=ref,
        mode=mode,
        inputs=inputs,
        write_prefix=write_prefix,
        expected_oci=expected_oci,
        timeout_s=timeout_s,
        require_prefix_placeholder=require_prefix_placeholder,
        extra=extra,
        build=build,
        env=env,
        branch=branch,
        user=user,
    )
    return orch.execute(opts)
