import asyncio
import time
import json
import os
from typing import Any, Dict, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from starlette.exceptions import WebSocketException
from .types import ConnectionRole, RunState
from .run_registry import registry
from .worker import spawn_worker
from .logging import info

app = FastAPI()


@app.get("/healthz")
def healthz():
    return {"ok": True, "digest": os.getenv("IMAGE_DIGEST", "unknown")}


@app.websocket("/run")
async def run_ws(ws: WebSocket):
    # One supervisor process per container; one worker process per run
    # Validate subprotocol BEFORE accepting - reject handshake if not offered
    required = "theory.run.v1"
    offered = [p.strip() for p in (ws.headers.get("sec-websocket-protocol") or "").split(",") if p.strip()]

    if required not in offered:
        # Raise before accept() to fail handshake (not post-accept close)
        raise WebSocketException(code=1002)

    await ws.accept(subprotocol=required)
    connection_id = f"conn-{int(time.time() * 1000)}"
    run_id: str | None = None
    role: ConnectionRole | None = None

    try:
        # First frame must be RunOpen
        msg = await ws.receive_json()
        if not isinstance(msg, dict) or msg.get("kind") != "RunOpen":
            await ws.close(code=1002)
            return
        content = msg.get("content") or {}
        run_id = str(content.get("run_id", "")).strip()

        if not run_id:
            await ws.close(code=1008)
            return

        # Payload is flattened - content is the payload
        payload = content

        # Default role to client (simplified - no multi-role protocol)
        role = ConnectionRole.CLIENT

        # Register connection
        run = await registry.get_or_create(run_id)
        await registry.add_connection(run_id, connection_id, ws, role)
        await ws.send_json({"kind": "Ack", "content": {"run_id": run_id}})

        # Client starts the run (if not running)
        if role is ConnectionRole.CLIENT and run.state == RunState.PENDING:
            await registry.update_state(run_id, RunState.RUNNING)
            info("ws.run.start", run_id=run_id)

            # Spawn worker process with an IPC queue + cancel event
            proc, events_q, cancel_ev = spawn_worker(payload)
            await registry.bind_worker(run_id, proc, cancel_ev)

            # Pump worker events → all listeners; capture terminal envelope
            run_start_time = time.time()

            async def pump():
                try:
                    loop = asyncio.get_running_loop()
                    while True:
                        ev = await loop.run_in_executor(None, events_q.get)  # blocking get
                        if ev is None:
                            break
                        # If terminal result, update state and log settlement
                        if ev.get("kind") == "RunResult":
                            status = (ev.get("content") or {}).get("status")
                            new_state = RunState.COMPLETED if status == "success" else RunState.ERROR
                            await registry.update_state(run_id, new_state)
                            elapsed_ms = int((time.time() - run_start_time) * 1000)
                            info("ws.run.settle", run_id=run_id, status=status, ms=elapsed_ms)
                        await registry.emit(run_id, ev)
                finally:
                    try:
                        proc.join(timeout=0.2)
                    except Exception:
                        pass

            pump_task = asyncio.create_task(pump())

            # Also watch for cancellation via registry (controller-driven)
            async def watch_cancel():
                # The registry flips cancel_ev; worker cooperatively exits; after grace, supervisor escalates
                grace_s = 5
                while True:
                    await asyncio.sleep(0.25)
                    st = await registry.state(run_id)
                    if st in (RunState.PREEMPTED, RunState.COMPLETED, RunState.ERROR):
                        break
                # If preempted, give worker grace then terminate if alive
                if st == RunState.PREEMPTED and proc.is_alive():
                    try:
                        proc.terminate()
                    except Exception:
                        pass
                    await asyncio.sleep(grace_s)
                    if proc.is_alive():
                        try:
                            proc.kill()
                        except Exception:
                            pass

            asyncio.create_task(watch_cancel())

        # Controllers read control frames; observers just keep the socket open
        if role is ConnectionRole.CONTROLLER:
            while True:
                m = await ws.receive_json()
                if m.get("kind") == "control":
                    await registry.apply_control(run_id, connection_id, m.get("content") or {})
        else:
            while True:
                await asyncio.sleep(30)

    except WebSocketDisconnect:
        pass
    finally:
        if run_id:
            await registry.remove_connection(run_id, connection_id)
            await registry.maybe_gc_run(run_id)
