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

    def invoke(
        self,
        ref: str,
        payload: Dict[str, Any],
        timeout_s: int,
        oci: Dict[str, Any],
        stream: bool = False,
    ) -> Dict[str, Any] | Iterator[Dict[str, Any]]:
        """
        Invoke a tool over WebSocket.
        - ref: tool ref (ns/name@ver) for logging
        - payload: same JSON you used to POST before, but must include put_urls
        - timeout_s: overall deadline for the run (adapter-side)
        - oci: {"ws_url": ".../run", "headers": {...}, "expected_digest": "..."} (resolved by control plane)
        - stream: if True, returns an iterator of events + final RunResult; else returns RunResult dict
        """
        if stream:
            return self._sync_event_iter(ref, payload, timeout_s, oci)
        # non-stream: drain events but only return final envelope
        events = self._sync_event_iter(ref, payload, timeout_s, oci)
        final_env = None
        for ev in events:
            if ev.get("kind") == "RunResult":
                final_env = ev["content"]
                break
        if final_env is None:
            raise WsError("Run finished without RunResult")
        return final_env

    # ---------------- Internals ----------------

    def _sync_event_iter(
        self, ref: str, payload: Dict[str, Any], timeout_s: int, oci: Dict[str, Any]
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
                async for ev in self._run_async(ref, payload, timeout_s, oci):
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
        self, ref: str, payload: Dict[str, Any], timeout_s: int, oci: Dict[str, Any]
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
                # Send RunOpen (first message)
                run_open = {
                    "kind": "RunOpen",
                    "content": {
                        "role": "client",
                        "execution_id": payload.get("execution_id"),
                        "start": True,
                        "payload": payload,
                    },
                    "t": _now_ms(),
                }
                await _send(ws, run_open)

                # Expect Ack or early RunResult
                while True:
                    if time.time() > deadline:
                        raise WsError("Timeout waiting for Ack")
                    raw = await asyncio.wait_for(ws.recv(), timeout=5)
                    msg = self._parse_msg(raw)
                    kind = msg.get("kind")
                    if kind == "Ack":
                        yield msg
                        break
                    if kind == "RunResult":
                        # Fast settle path (no streams)
                        env = msg.get("content") or {}
                        self._validate_envelope(env, expected_digest)
                        yield msg
                        return
                    # Some runtimes may emit an early Event; surface it
                    if kind in ("Event", "Log", "Token", "Frame"):
                        yield msg
                        continue
                    # Ignore unknown kinds

                # Stream loop
                while True:
                    if time.time() > deadline:
                        raise WsError("Timeout waiting for RunResult")
                    raw = await asyncio.wait_for(ws.recv(), timeout=15)
                    msg = self._parse_msg(raw)
                    kind = msg.get("kind")
                    if kind == "RunResult":
                        env = msg.get("content") or {}
                        self._validate_envelope(env, expected_digest)
                        yield msg
                        break
                    if kind in ("Event", "Log", "Token", "Frame"):
                        yield msg
                    # otherwise ignore
        except TimeoutError:
            raise WsError("WebSocket timeout")
        except websockets.exceptions.ConnectionClosedOK:
            # normal close after RunResult
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

    def _validate_envelope(self, env: Dict[str, Any], expected_digest: str | None) -> None:
        """
        Validate envelope structure and drift.

        Contract: Tool always returns an envelope with status="success" or "error".
        - status="error" is a VALID envelope (tool-level failure)
        - Only raise for TRANSPORT/PROTOCOL failures (drift, malformed envelope)
        """
        status = env.get("status")

        # Validate envelope has required status field
        if status not in ("success", "error"):
            raise WsError(f"Invalid envelope: missing or bad status (got {status!r})")

        # For success envelopes, validate structure
        if status == "success":
            # index_path discipline (only for success)
            index_path = env.get("index_path") or ""
            if not index_path.endswith("outputs.json"):
                raise WsError("Success envelope must have index_path ending with outputs.json")

        # For error envelopes, ensure error field present
        if status == "error" and "error" not in env:
            raise WsError("Error envelope missing 'error' field")

        # Drift check (applies to both success and error)
        if expected_digest:
            got = (((env.get("meta") or {}).get("image_digest")) or "").strip()
            if not got:
                raise DriftError("Envelope missing meta.image_digest for drift check")
            if expected_digest != got:
                raise DriftError(f"Digest drift: expected {expected_digest}, got {got}")
