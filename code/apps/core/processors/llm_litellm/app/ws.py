import asyncio
import time
import json
import uuid
from typing import Any, Dict, Callable, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from .types import ConnectionRole, RunState
from .run_registry import registry
from .handler import entry
from .logging import info

app = FastAPI()


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.websocket("/run")
async def run_ws(ws: WebSocket):
    await ws.accept(subprotocol="theory.run.v1")
    connection_id = f"conn-{int(time.time() * 1000)}"
    execution_id: str | None = None
    role: ConnectionRole | None = None

    try:
        # First frame must be RunOpen
        msg = await ws.receive_json()
        if not isinstance(msg, dict) or msg.get("kind") != "RunOpen":
            await ws.close(code=1002)
            return
        content = msg.get("content") or {}
        role_s = str(content.get("role", "")).lower()
        execution_id = str(content.get("execution_id", "")).strip()
        payload = content.get("payload") or {}

        if role_s not in ("client", "controller", "observer") or not execution_id:
            await ws.close(code=1008)
            return
        role = ConnectionRole[role_s.upper()]

        # TODO: verify ticket claims here (execution_id, scopes)

        # Register connection
        run = await registry.get_or_create(execution_id)
        await registry.add_connection(execution_id, connection_id, ws, role)
        await ws.send_json({"kind": "Ack", "content": {"execution_id": execution_id}})

        # Client role may start the run if not running
        if role is ConnectionRole.CLIENT and run.state == RunState.PENDING:
            await registry.update_state(execution_id, RunState.RUNNING)
            info("ws.run.start", execution_id=execution_id)

            async def fanout(ev: Dict[str, Any]):  # async bridge
                await registry.emit(execution_id, ev)

            # Run entry in thread; capture emitted events via queueing
            loop = asyncio.get_running_loop()

            def emit_sync(ev: Dict[str, Any]):
                loop.call_soon_threadsafe(asyncio.create_task, fanout(ev))

            start = time.monotonic()
            try:
                env = await loop.run_in_executor(None, entry, payload, emit_sync)
                await registry.update_state(execution_id, RunState.COMPLETED)
                # Fanout terminal result to ALL
                await registry.emit(execution_id, {"kind": "RunResult", "content": env})
                await ws.send_json({"kind": "RunResult", "content": env})
                info(
                    "ws.run.settle",
                    execution_id=execution_id,
                    status=env.get("status"),
                    elapsed_ms=int((time.monotonic() - start) * 1000),
                )
            except asyncio.CancelledError:
                await registry.update_state(execution_id, RunState.PREEMPTED)
                term = {
                    "status": "error",
                    "execution_id": execution_id,
                    "error": {"code": "ERR_PREEMPTED", "message": "cancelled"},
                    "meta": {},
                }
                await registry.emit(execution_id, {"kind": "RunResult", "content": term})
                await ws.send_json({"kind": "RunResult", "content": term})
            except Exception as e:
                await registry.update_state(execution_id, RunState.ERROR)
                term = {
                    "status": "error",
                    "execution_id": execution_id,
                    "error": {"code": "ERR_RUNTIME", "message": str(e)},
                    "meta": {},
                }
                await registry.emit(execution_id, {"kind": "RunResult", "content": term})
                await ws.send_json({"kind": "RunResult", "content": term})

        # If controller, read control frames; observers just park
        if role is ConnectionRole.CONTROLLER:
            while True:
                m = await ws.receive_json()
                if m.get("kind") == "control":
                    await registry.apply_control(execution_id, connection_id, m.get("content") or {})
        else:
            # keep-alive loop; fanout is handled by registry
            while True:
                await asyncio.sleep(30)

    except WebSocketDisconnect:
        pass
    finally:
        if execution_id:
            await registry.remove_connection(execution_id, connection_id)
            await registry.maybe_gc_run(execution_id)
