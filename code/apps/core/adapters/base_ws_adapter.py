# code/apps/core/adapters/base_ws_adapter.py
from __future__ import annotations
import asyncio
import json
import threading
import time
from typing import Any, AsyncIterator, Dict, Iterator, Optional, Union

import httpx
import websockets
from websockets.client import connect as ws_connect


class WsError(RuntimeError):
    pass


class DriftError(WsError):
    pass


def _now_ms() -> int:
    return int(time.time() * 1000)


class BaseWsAdapter:
    """
    Transport-only WebSocket adapter.
    - Opens WS to /run
    - Sends RunInvoke (payload already contains put_urls)
    - Streams events (token|frame|log|event) if stream=True
    - Receives final RunResult envelope, validates, and returns / yields
    """

    def __init__(
        self,
        *,
        logger=None,
        http_client: httpx.Client | None = None,
        connect_timeout_s: int = 15,
        ping_interval_s: int = 25,
    ):
        self.logger = logger or (lambda **kw: None)
        self.http = http_client or httpx.Client(timeout=10)
        self.connect_timeout_s = connect_timeout_s
        self.ping_interval_s = ping_interval_s

    # ---------------- Public API ----------------

    def invoke_run(self, run) -> Dict[str, Any]:
        """
        High-level invocation from Run model.
        Loads Tool, constructs payload with presigned URLs, invokes, returns envelope.
        """
        from apps.tools.models import Tool
        from django.conf import settings
        import platform

        # Load tool for runtime config and digest
        try:
            tool = Tool.objects.get(ref=run.ref)
        except Tool.DoesNotExist:
            raise WsError(f"Tool not found: {run.ref}")

        # Detect architecture for digest selection
        arch = platform.machine()
        if arch == "x86_64":
            expected_digest = tool.digest_amd64
        elif arch in ("arm64", "aarch64"):
            expected_digest = tool.digest_arm64
        else:
            expected_digest = tool.digest_amd64  # fallback

        # Construct payload with presigned PUT URLs
        payload = self._build_payload(run)

        # Invoke with tool timeout
        oci = {"expected_digest": expected_digest}
        return self.invoke(run.ref, payload, tool.timeout_s, oci, stream=False)

    def _build_payload(self, run) -> Dict[str, Any]:
        """
        Build invocation payload with hydrated inputs and presigned output URLs.

        Hydrates world:// URIs in inputs to presigned GET URLs.
        Generates presigned PUT URLs for outputs.
        """
        from backend.storage.service import StorageService
        from django.conf import settings

        storage = StorageService()
        bucket = settings.STORAGE.get("BUCKET")

        # Get tool for timeout and output declarations
        from apps.tools.models import Tool

        try:
            tool = Tool.objects.get(ref=run.ref)
            timeout = tool.timeout_s
            output_paths = [o.get("path") for o in tool.outputs_decl if o.get("path")]
        except Tool.DoesNotExist:
            timeout = 3600
            output_paths = []

        # Hydrate inputs: convert world:// URIs to presigned GET URLs
        hydrated_inputs = self._hydrate_inputs(run.inputs, run.world.id, bucket, storage, timeout)

        # Generate presigned PUT URLs for declared outputs
        prefix = run.write_prefix.lstrip("/").rstrip("/")
        outputs = {}
        for path in output_paths:
            outputs[path] = storage.generate_presigned_put_url(
                bucket=bucket, key=f"{prefix}/{path}", expires_in=timeout
            )

        # Always include outputs.json index
        outputs["outputs.json"] = storage.generate_presigned_put_url(
            bucket=bucket, key=f"{prefix}/outputs.json", expires_in=timeout
        )

        return {
            "run_id": str(run.id),
            "mode": run.mode,
            "inputs": hydrated_inputs,
            "outputs": outputs,
        }

    def _hydrate_inputs(
        self, inputs: Dict[str, Any], world_id: str, bucket: str, storage, timeout: int
    ) -> Dict[str, Any]:
        """
        Recursively hydrate world:// URIs to presigned GET URLs.

        Handles:
        - world://{world}/{run}/{path} → presigned GET URL
        - world://{world}/{run}/key?data={json} → leaves as-is (protocol layer handles)
        - Nested dicts and lists
        """
        if isinstance(inputs, dict):
            return {k: self._hydrate_inputs(v, world_id, bucket, storage, timeout) for k, v in inputs.items()}
        elif isinstance(inputs, list):
            return [self._hydrate_inputs(item, world_id, bucket, storage, timeout) for item in inputs]
        elif isinstance(inputs, str) and inputs.startswith("world://"):
            # Check if it's a scalar (has ?data=)
            if "?data=" in inputs:
                # Scalar artifact - protocol layer will extract data
                return inputs

            # File artifact - generate presigned GET URL
            # Parse: world://{world_id}/{run_id}/{path}
            uri_path = inputs.replace("world://", "")
            parts = uri_path.split("/", 2)

            if len(parts) < 3:
                raise ValueError(f"Invalid world:// URI format: {inputs}")

            uri_world_id, run_id, path = parts

            # Security: ensure artifact is from same world
            if uri_world_id != str(world_id):
                raise PermissionError(f"Cannot access artifacts from other worlds: {inputs}")

            # Generate presigned GET URL
            s3_key = f"{uri_world_id}/{run_id}/{path}"
            return storage.generate_presigned_get_url(bucket=bucket, key=s3_key, expires_in=timeout)
        else:
            # Primitive value or non-world URI
            return inputs

    def invoke(
        self,
        ref: str,
        request: Dict[str, Any],
        timeout_s: int,
        oci: Dict[str, Any],
        stream: bool = False,
    ) -> Dict[str, Any] | Iterator[Dict[str, Any]]:
        """
        Invoke a tool over WebSocket.
        - ref: tool ref (ns/name@ver) for logging
        - request: Request message with control/inputs/outputs
        - timeout_s: overall deadline for the run (adapter-side)
        - oci: {"ws_url": ".../run", "headers": {...}, "expected_digest": "..."} (resolved by control plane)
        - stream: if True, returns an iterator of events + final Response; else returns Response dict
        """
        if stream:
            return self._sync_event_iter(ref, request, timeout_s, oci)
        # non-stream: drain events but only return final Response
        events = self._sync_event_iter(ref, request, timeout_s, oci)
        final_response = None
        for ev in events:
            if ev.get("kind") == "Response" and ev.get("control", {}).get("final"):
                final_response = ev
                break
        if final_response is None:
            raise WsError("Run finished without Response")
        return final_response

    # ---------------- Internals ----------------

    def _sync_event_iter(
        self, ref: str, request: Dict[str, Any], timeout_s: int, oci: Dict[str, Any]
    ) -> Iterator[Dict[str, Any]]:
        """
        Wrap the async event generator in a blocking iterator.
        """
        import queue
        import concurrent.futures

        # Use thread-safe queue
        q = queue.Queue()

        async def runner():
            try:
                async for ev in self._run_async(ref, request, timeout_s, oci):
                    q.put(ev)
            finally:
                q.put(None)  # sentinel

        # Run async function in thread
        def run_async():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(runner())
            finally:
                loop.close()

        t = threading.Thread(target=run_async, daemon=True)
        t.start()

        try:
            while True:
                ev = q.get()  # blocking, thread-safe
                if ev is None:
                    break
                yield ev
        finally:
            t.join(timeout=1.0)  # Give thread time to cleanup

    async def _run_async(
        self, ref: str, request: Dict[str, Any], timeout_s: int, oci: Dict[str, Any]
    ) -> AsyncIterator[Dict[str, Any]]:
        ws_url: str = oci.get("ws_url") or ""
        headers: Dict[str, str] = oci.get("headers") or {}
        expected_digest: str | None = oci.get("expected_digest")

        if not ws_url:
            raise WsError("Missing ws_url in oci")

        deadline = time.time() + max(5, timeout_s or 600)

        async def _send(ws, obj: Dict[str, Any]):
            await ws.send(json.dumps(obj, separators=(",", ":")))

        # Connect
        self.logger(event="ws.connect.start", ref=ref, ws_url=ws_url)
        try:
            async with ws_connect(
                ws_url,
                extra_headers=headers,
                open_timeout=self.connect_timeout_s,
                ping_interval=self.ping_interval_s,
                ping_timeout=10,
                max_size=8 * 1024 * 1024,  # 8MB cap; bigger media should use PUT
                subprotocols=["theory.run.v1"],
            ) as ws:
                self.logger(event="ws.connect.ok", ref=ref)
                # Send Request (first message)
                await _send(ws, request)

                # Expect Ack or early Response
                while True:
                    if time.time() > deadline:
                        raise WsError("Timeout waiting for Ack")
                    raw = await asyncio.wait_for(ws.recv(), timeout=5)
                    msg = self._parse_msg(raw)
                    kind = msg.get("kind")
                    if kind == "Ack":
                        yield msg
                        break
                    if kind == "Response" and msg.get("control", {}).get("final"):
                        # Fast settle path (no streams)
                        self._validate_response(msg, expected_digest)
                        yield msg
                        return
                    # Some runtimes may emit an early Event; surface it
                    if kind in ("Event", "Log", "Token", "Frame", "Response"):
                        yield msg
                        continue
                    # Ignore unknown kinds

                # Stream loop
                while True:
                    if time.time() > deadline:
                        raise WsError("Timeout waiting for Response")
                    raw = await asyncio.wait_for(ws.recv(), timeout=15)
                    msg = self._parse_msg(raw)
                    kind = msg.get("kind")
                    if kind == "Response" and msg.get("control", {}).get("final"):
                        self._validate_response(msg, expected_digest)
                        yield msg
                        break
                    if kind in ("Event", "Log", "Token", "Frame", "Response"):
                        yield msg
                    # otherwise ignore
        except TimeoutError:
            raise WsError("WebSocket timeout")
        except websockets.exceptions.ConnectionClosedOK:
            # normal close after Response
            return
        except websockets.exceptions.ConnectionClosedError as e:
            raise WsError(f"WebSocket closed unexpectedly: {e.code} {e.reason}") from e

    def _parse_msg(self, raw: bytes | str) -> Dict[str, Any]:
        if isinstance(raw, bytes | bytearray):
            raw = raw.decode("utf-8", "replace")
        try:
            return json.loads(raw)
        except Exception:
            return {"kind": "Error", "content": {"message": "non-json frame"}, "raw": raw}

    def _validate_response(self, response: Dict[str, Any], expected_digest: str | None) -> None:
        """
        Validate Response structure and drift.

        Contract: Tool always returns a Response with status="success" or "error".
        - status="error" is a VALID response (tool-level failure)
        - Only raise for TRANSPORT/PROTOCOL failures (drift, malformed response)
        """
        control = response.get("control", {})
        status = control.get("status")

        # Validate response has required status field
        if status not in ("success", "error"):
            raise WsError(f"Invalid response: missing or bad status (got {status!r})")

        # For error responses, ensure error field present
        if status == "error" and "error" not in response:
            raise WsError("Error response missing 'error' field")

        # Drift check - skip for now, will revisit after refactor complete
        # TODO: Implement digest validation from container metadata
