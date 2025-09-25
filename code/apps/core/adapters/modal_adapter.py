"""
Modal adapter: HTTP transport-only invocation of deployed web endpoints.

CRITICAL: Modal Labs only supports AMD64 (linux/amd64) container images.
ARM64 images will fail with "image architecture arm64 not supported" error.

Contract:
- Deploy Modal function with FastAPI app exposed as web endpoint
- POST payload to deployed /run or /run-stream endpoint
- Return validated envelope
- Enforce digest drift detection
"""

import json
import time
import requests
from typing import Any, Dict, Iterator, Optional
from libs.runtime_common.envelope import is_valid_envelope, error_envelope
from libs.runtime_common.logging import log


def _extract_sha256(ref_or_digest: str) -> str:
    """
    Extract SHA256 digest from OCI reference or digest string.

    Accepts:
      - 'ghcr.io/owner/repo@sha256:abcd...'
      - 'sha256:abcd...'
    Returns: 'sha256:abcd...' or '' if not found.
    """
    s = (ref_or_digest or "").strip()
    if not s:
        return ""
    s = s.lower()
    if "@sha256:" in s:
        return "sha256:" + s.split("@sha256:", 1)[1]
    if s.startswith("sha256:"):
        return s
    return ""


class ModalAdapter:
    """Modal web endpoint adapter."""

    def invoke(
        self, *, ref: str, payload: Dict[str, Any], timeout_s: int, oci: str | None = None, stream: bool = False, **_
    ) -> Dict[str, Any] | Iterator[Dict[str, Any]]:
        """
        Invoke processor via Modal web endpoint.

        1. Compute Modal app name from ref and environment
        2. Construct web endpoint URL
        3. POST to /run or /run-stream
        4. Return validated envelope with digest check
        """
        execution_id = payload.get("execution_id", "")

        # Compute Modal context using same logic as modalctl
        import os
        from apps.core.management.commands._modal_common import modal_app_name

        environment = os.getenv("MODAL_ENVIRONMENT", "dev")
        user = os.getenv("USER", "unknown")
        branch = os.getenv("BRANCH", "dev")

        if environment == "dev":
            app_name = modal_app_name(ref, env=environment, branch=branch, user=user)
        else:
            app_name = modal_app_name(ref, env=environment)

        log(
            "info",
            "adapter.invoke.start",
            adapter="modal",
            ref=ref,
            app_name=app_name,
            environment=environment,
            execution_id=execution_id,
            mode=payload.get("mode"),
            timeout_s=timeout_s,
            expected_oci=oci,
        )

        # Use Modal SDK to get actual web URL - no string construction
        try:
            import modal

            app = modal.App.lookup(app_name)
            fn = modal.Function.from_name(app_name, "fastapi_app")
            base_url = fn.web_url  # Source of truth from Modal SDK
        except Exception as e:
            log("error", "adapter.modal.lookup_failed", adapter="modal", app_name=app_name, error=str(e))
            return error_envelope(
                execution_id,
                "ERR_ADAPTER_INVOCATION",
                f"Failed to resolve Modal app URL: {e}",
                {"env_fingerprint": "modal_error"},
            )

        endpoint = "/run-stream" if stream else "/run"
        url = f"{base_url}{endpoint}"

        log(
            "debug",
            "adapter.http.request",
            adapter="modal",
            url=url,
            execution_id=execution_id,
            payload_size=len(json.dumps(payload)),
        )

        try:
            if stream:
                # SSE streaming
                return self._handle_stream(url, payload, timeout_s, execution_id, oci)
            else:
                # Synchronous request
                start_time = time.time()

                # Modal web endpoints don't need auth for deployed functions
                headers = {"Content-Type": "application/json"}

                resp = requests.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=timeout_s + 10,  # Buffer for Modal cold start
                )
                elapsed_ms = int((time.time() - start_time) * 1000)

                if resp.status_code == 404:
                    msg = f"Modal app not found: {app_name} in {environment}"
                    log("error", "adapter.modal.not_found", adapter="modal", app_name=app_name, environment=environment)
                    return error_envelope(
                        execution_id=execution_id, code="ERR_MODAL_NOT_FOUND", message=msg, env_fingerprint="modal_404"
                    )

                if resp.status_code != 200:
                    msg = f"HTTP {resp.status_code}: {resp.text[:200]}"
                    log(
                        "error",
                        "adapter.http.error",
                        adapter="modal",
                        status_code=resp.status_code,
                        message=msg,
                        elapsed_ms=elapsed_ms,
                    )
                    return error_envelope(
                        execution_id=execution_id,
                        code="ERR_ADAPTER_INVOCATION",
                        message=msg,
                        env_fingerprint="modal_http_error",
                    )

                # Parse and validate envelope
                try:
                    envelope = resp.json()
                except json.JSONDecodeError as e:
                    msg = f"Invalid JSON response: {e}"
                    log("error", "adapter.response.invalid", adapter="modal", message=msg)
                    return error_envelope(
                        execution_id=execution_id,
                        code="ERR_ADAPTER_INVOCATION",
                        message=msg,
                        env_fingerprint="modal_json_error",
                    )

                # Validate envelope
                ok, why = is_valid_envelope(envelope)
                if not ok:
                    msg = f"Invalid envelope: {why}"
                    log("error", "adapter.envelope.invalid", adapter="modal", message=msg)
                    return error_envelope(
                        execution_id=execution_id,
                        code="ERR_ADAPTER_INVOCATION",
                        message=msg,
                        env_fingerprint="modal_validation_error",
                    )

                # Digest drift check (required for Modal) - normalize both for comparison
                if oci:
                    got_raw = envelope.get("meta", {}).get("image_digest", "")
                    if not got_raw:
                        msg = "Modal envelope missing image_digest in meta"
                        log("error", "adapter.digest.missing", adapter="modal")
                        return error_envelope(
                            execution_id=execution_id,
                            code="ERR_REGISTRY_MISMATCH",
                            message=msg,
                            env_fingerprint="modal_digest_missing",
                        )

                    # Normalize both expected and received digests for comparison
                    expected_digest = _extract_sha256(oci)
                    got_digest = _extract_sha256(got_raw)

                    if expected_digest and got_digest and expected_digest != got_digest:
                        msg = f"Image digest mismatch: got={got_digest} expected={expected_digest}"
                        log(
                            "error",
                            "adapter.digest.mismatch",
                            adapter="modal",
                            got_raw=got_raw,
                            got_digest=got_digest,
                            expected_oci=oci,
                            expected_digest=expected_digest,
                        )
                        return error_envelope(
                            execution_id=execution_id,
                            code="ERR_REGISTRY_MISMATCH",
                            message=msg,
                            env_fingerprint="modal_digest_error",
                        )

                log(
                    "info",
                    "adapter.invoke.complete",
                    adapter="modal",
                    execution_id=execution_id,
                    status=envelope.get("status"),
                    elapsed_ms=elapsed_ms,
                )

                return envelope

        except requests.Timeout:
            msg = f"Modal request timed out after {timeout_s}s"
            log("error", "adapter.timeout", adapter="modal", message=msg)
            return error_envelope(
                execution_id=execution_id, code="ERR_ADAPTER_TIMEOUT", message=msg, env_fingerprint="modal_timeout"
            )
        except requests.RequestException as e:
            msg = f"HTTP error: {e}"
            log("error", "adapter.http.error", adapter="modal", message=msg)
            return error_envelope(
                execution_id=execution_id,
                code="ERR_ADAPTER_INVOCATION",
                message=msg,
                env_fingerprint="modal_request_error",
            )
        except Exception as e:
            msg = f"Unexpected error: {e}"
            log("error", "adapter.invoke.error", adapter="modal", message=msg)
            return error_envelope(
                execution_id=execution_id, code="ERR_ADAPTER_INVOCATION", message=msg, env_fingerprint="modal_error"
            )

    def _handle_stream(
        self, url: str, payload: Dict[str, Any], timeout_s: int, execution_id: str, oci: str | None
    ) -> Iterator[Dict[str, Any]]:
        """Handle SSE streaming response."""
        try:
            import os

            headers = {}
            modal_token = os.getenv("MODAL_TOKEN_ID")
            if modal_token:
                headers["Authorization"] = f"Bearer {modal_token}"

            resp = requests.post(url, json=payload, headers=headers, stream=True, timeout=timeout_s)

            event_type = None
            for line in resp.iter_lines():
                if line:
                    line = line.decode("utf-8")
                    if line.startswith("event:"):
                        event_type = line[6:].strip()
                    elif line.startswith("data:"):
                        data = json.loads(line[5:].strip())

                        # If this is the final envelope, validate digest
                        if event_type == "done" and oci:
                            got = data.get("meta", {}).get("image_digest", "")
                            if got and got != oci:
                                yield {
                                    "event": "error",
                                    "data": error_envelope(
                                        execution_id=execution_id,
                                        code="ERR_REGISTRY_MISMATCH",
                                        message=f"Digest mismatch: {got} != {oci}",
                                        env_fingerprint="modal_stream_digest_error",
                                    ),
                                }
                                break

                        yield {"event": event_type, "data": data}

                        # If done event, break
                        if event_type == "done":
                            break

        except Exception as e:
            yield {
                "event": "error",
                "data": error_envelope(
                    execution_id=execution_id, code="ERR_STREAM", message=str(e), env_fingerprint="modal_stream_error"
                ),
            }
