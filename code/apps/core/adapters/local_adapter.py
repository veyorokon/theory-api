"""
Local (Docker) adapter: HTTP transport-only execution.

Contract:
- Start container from registry digest
- Health poll /healthz endpoint
- POST payload to /run or /run-stream
- Return validated envelope
- Optional digest drift check
"""

import json
import time
import requests
import subprocess
import platform
from typing import Any, Dict, Iterator
from libs.runtime_common.envelope import is_valid_envelope, error_envelope
from libs.runtime_common.logging import log


class LocalAdapter:
    """Docker-backed HTTP adapter."""

    def invoke(
        self, *, ref: str, payload: Dict[str, Any], timeout_s: int, oci: str | None = None, stream: bool = False, **_
    ) -> Dict[str, Any] | Iterator[Dict[str, Any]]:
        """
        Execute processor locally via Docker HTTP.

        1. Resolve image digest based on host architecture
        2. Start container with port mapping
        3. Health poll /healthz
        4. POST to /run or /run-stream
        5. Return validated envelope
        """
        execution_id = payload.get("execution_id", "")

        log(
            "info",
            "adapter.invoke.start",
            adapter="local",
            ref=ref,
            execution_id=execution_id,
            mode=payload.get("mode"),
            timeout_s=timeout_s,
        )

        # Resolve image based on architecture
        image = self._resolve_image(ref, oci)
        if not image:
            msg = f"No image found for {ref}"
            log("error", "adapter.invoke.error", adapter="local", error="ERR_NO_IMAGE", message=msg)
            return error_envelope(
                execution_id=execution_id, code="ERR_ADAPTER_INVOCATION", message=msg, env_fingerprint="local_error"
            )

        # Start container
        container_id = None
        try:
            # Pull image if needed
            log("debug", "adapter.docker.pull", image=image)
            subprocess.run(["docker", "pull", image], capture_output=True, check=False)

            # Start container with port mapping
            start_cmd = ["docker", "run", "-d", "-p", "8000:8000", "--rm", image]

            log("debug", "adapter.docker.start", command=" ".join(start_cmd))
            result = subprocess.run(start_cmd, capture_output=True, text=True, check=True)
            container_id = result.stdout.strip()

            log("debug", "adapter.docker.started", container_id=container_id[:12])

            # Health poll (max 3 seconds)
            health_url = "http://localhost:8000/healthz"
            for attempt in range(6):  # 6 attempts * 0.5s = 3s max
                try:
                    resp = requests.get(health_url, timeout=1)
                    if resp.status_code == 200:
                        health_data = resp.json()
                        log("debug", "adapter.health.ok", image_digest=health_data.get("image_digest"), attempt=attempt)
                        break
                except requests.RequestException:
                    if attempt < 5:
                        time.sleep(0.5)
                    else:
                        raise Exception("Health check failed after 3 seconds")

            # POST to endpoint
            endpoint = "/run-stream" if stream else "/run"
            url = f"http://localhost:8000{endpoint}"

            log(
                "debug",
                "adapter.http.request",
                url=url,
                execution_id=execution_id,
                payload_size=len(json.dumps(payload)),
            )

            if stream:
                # SSE streaming
                return self._handle_stream(url, payload, timeout_s, execution_id)
            else:
                # Synchronous request
                start_time = time.time()
                resp = requests.post(
                    url,
                    json=payload,
                    timeout=timeout_s + 5,  # Small buffer over handler timeout
                )
                elapsed_ms = int((time.time() - start_time) * 1000)

                if resp.status_code != 200:
                    msg = f"HTTP {resp.status_code}: {resp.text[:200]}"
                    log(
                        "error",
                        "adapter.http.error",
                        adapter="local",
                        status_code=resp.status_code,
                        message=msg,
                        elapsed_ms=elapsed_ms,
                    )
                    return error_envelope(
                        execution_id=execution_id,
                        code="ERR_ADAPTER_INVOCATION",
                        message=msg,
                        env_fingerprint="local_http_error",
                    )

                # Parse and validate envelope
                try:
                    envelope = resp.json()
                except json.JSONDecodeError as e:
                    msg = f"Invalid JSON response: {e}"
                    log("error", "adapter.response.invalid", adapter="local", message=msg)
                    return error_envelope(
                        execution_id=execution_id,
                        code="ERR_ADAPTER_INVOCATION",
                        message=msg,
                        env_fingerprint="local_json_error",
                    )

                # Validate envelope
                ok, why = is_valid_envelope(envelope)
                if not ok:
                    msg = f"Invalid envelope: {why}"
                    log("error", "adapter.envelope.invalid", adapter="local", message=msg)
                    return error_envelope(
                        execution_id=execution_id,
                        code="ERR_ADAPTER_INVOCATION",
                        message=msg,
                        env_fingerprint="local_validation_error",
                    )

                # Optional digest drift check
                if oci:
                    got = envelope.get("meta", {}).get("image_digest", "")
                    if got and got != oci:
                        msg = f"Digest mismatch: {got} != {oci}"
                        log("error", "adapter.digest.mismatch", adapter="local", got=got, expected=oci)
                        return error_envelope(
                            execution_id=execution_id,
                            code="ERR_REGISTRY_MISMATCH",
                            message=msg,
                            env_fingerprint="local_digest_error",
                        )

                log(
                    "info",
                    "adapter.invoke.complete",
                    adapter="local",
                    execution_id=execution_id,
                    status=envelope.get("status"),
                    elapsed_ms=elapsed_ms,
                )

                return envelope

        except subprocess.CalledProcessError as e:
            msg = f"Docker error: {e.stderr[:200] if e.stderr else str(e)}"
            log("error", "adapter.docker.error", adapter="local", message=msg)
            return error_envelope(
                execution_id=execution_id,
                code="ERR_ADAPTER_INVOCATION",
                message=msg,
                env_fingerprint="local_docker_error",
            )
        except requests.RequestException as e:
            msg = f"HTTP error: {e}"
            log("error", "adapter.http.error", adapter="local", message=msg)
            return error_envelope(
                execution_id=execution_id,
                code="ERR_ADAPTER_INVOCATION",
                message=msg,
                env_fingerprint="local_request_error",
            )
        except Exception as e:
            msg = f"Unexpected error: {e}"
            log("error", "adapter.invoke.error", adapter="local", message=msg)
            return error_envelope(
                execution_id=execution_id, code="ERR_ADAPTER_INVOCATION", message=msg, env_fingerprint="local_error"
            )
        finally:
            # Stop container
            if container_id:
                try:
                    subprocess.run(["docker", "stop", container_id], capture_output=True, check=False)
                    log("debug", "adapter.docker.stopped", container_id=container_id[:12])
                except:
                    pass

    def _resolve_image(self, ref: str, oci: str | None) -> str | None:
        """Resolve image based on architecture and registry."""
        if oci:
            # Use provided OCI digest
            return oci

        # Load from registry
        try:
            from apps.core.registry.loader import load_processor_spec

            spec = load_processor_spec(ref)

            # Detect host architecture
            arch = platform.machine().lower()
            if arch == "x86_64":
                arch = "amd64"
            elif arch in ["aarch64", "arm64"]:
                arch = "arm64"

            # Get platform-specific digest
            platforms = spec.get("image", {}).get("platforms", {})
            if arch in platforms:
                return platforms[arch]

            # Fall back to default platform
            default_platform = spec.get("image", {}).get("default_platform", "amd64")
            return platforms.get(default_platform)

        except Exception as e:
            log("error", "adapter.image.resolve.error", error=str(e))
            return None

    def _handle_stream(
        self, url: str, payload: Dict[str, Any], timeout_s: int, execution_id: str
    ) -> Iterator[Dict[str, Any]]:
        """Handle SSE streaming response."""
        try:
            resp = requests.post(url, json=payload, stream=True, timeout=timeout_s)

            for line in resp.iter_lines():
                if line:
                    line = line.decode("utf-8")
                    if line.startswith("event:"):
                        event_type = line[6:].strip()
                    elif line.startswith("data:"):
                        data = json.loads(line[5:].strip())
                        yield {"event": event_type, "data": data}

                        # If done event, break
                        if event_type == "done":
                            break

        except Exception as e:
            yield {
                "event": "error",
                "data": error_envelope(
                    execution_id=execution_id, code="ERR_STREAM", message=str(e), env_fingerprint="local_stream_error"
                ),
            }
