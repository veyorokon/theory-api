import asyncio
import time
from typing import Dict, Set, Optional, Any, Tuple
from multiprocessing.process import BaseProcess
from multiprocessing.synchronize import Event as MpEvent
from .types import ConnectionRole, RunState
from .logging import info


class Run:
    __slots__ = ("eid", "state", "conns", "budgets", "fanout_q", "fanout_task", "proc", "cancel_ev")

    def __init__(self, eid: str):
        self.eid = eid
        self.state = RunState.PENDING
        self.conns: Dict[ConnectionRole, Set[Any]] = {
            ConnectionRole.CLIENT: set(),
            ConnectionRole.CONTROLLER: set(),
            ConnectionRole.OBSERVER: set(),
        }
        self.budgets = {"tokens": None, "time_s": None}
        self.fanout_q: asyncio.Queue = asyncio.Queue(maxsize=2048)
        self.fanout_task: asyncio.Task | None = None
        self.proc: BaseProcess | None = None
        self.cancel_ev: MpEvent | None = None


class RunRegistry:
    def __init__(self):
        self._runs: Dict[str, Run] = {}
        self._lock = asyncio.Lock()

    async def get_or_create(self, eid: str) -> Run:
        async with self._lock:
            run = self._runs.get(eid)
            if not run:
                run = Run(eid)
                self._runs[eid] = run
                run.fanout_task = asyncio.create_task(self._fanout_loop(run))
                info("run.registry.open", execution_id=eid)
            return run

    async def state(self, eid: str) -> RunState:
        r = await self.get_or_create(eid)
        return r.state

    async def add_connection(self, eid: str, cid: str, ws, role: ConnectionRole):
        run = await self.get_or_create(eid)
        # annotate connection id for GC
        ws._cid = cid
        run.conns[role].add(ws)
        info(
            "ws.connect.ok",
            execution_id=eid,
            role=role.name.lower(),
            conns={r.name.lower(): len(s) for r, s in run.conns.items()},
        )

    async def remove_connection(self, eid: str, cid: str):
        run = self._runs.get(eid)
        if not run:
            return
        for s in run.conns.values():
            for ws in list(s):
                if getattr(ws, "_cid", None) == cid:
                    s.discard(ws)
        info("ws.close", execution_id=eid, conns={r.name.lower(): len(s) for r, s in run.conns.items()})

    async def update_state(self, eid: str, state: RunState):
        run = await self.get_or_create(eid)
        run.state = state

    async def set_budget(self, eid: str, tokens=None, time_s=None):
        run = await self.get_or_create(eid)
        if tokens is not None:
            run.budgets["tokens"] = tokens
        if time_s is not None:
            run.budgets["time_s"] = time_s

    async def bind_worker(self, eid: str, proc: BaseProcess, cancel_ev: MpEvent):
        run = await self.get_or_create(eid)
        run.proc = proc
        run.cancel_ev = cancel_ev

    async def emit(self, eid: str, ev: dict):
        run = await self.get_or_create(eid)
        if run.fanout_q.full() and ev.get("kind") == "Token":
            return
        await run.fanout_q.put(ev)

    async def fanout_event(self, eid: str, ev: dict):
        await self.emit(eid, ev)

    async def maybe_gc_run(self, eid: str):
        run = self._runs.get(eid)
        if not run:
            return
        if all(len(s) == 0 for s in run.conns.values()) and run.state in (
            RunState.COMPLETED,
            RunState.PREEMPTED,
            RunState.ERROR,
        ):
            if run.fanout_task:
                await run.fanout_q.put(None)
                try:
                    await asyncio.wait_for(run.fanout_task, timeout=1.0)
                except Exception:
                    pass
            self._runs.pop(eid, None)
            info("run.registry.close", execution_id=eid)

    async def apply_control(self, eid: str, controller_id: str, content: dict):
        op = (content.get("op") or "").lower()
        run = await self.get_or_create(eid)

        if op == "preempt":
            # mark state
            run.state = RunState.PREEMPTED
            # signal worker cooperatively
            if run.cancel_ev:
                try:
                    run.cancel_ev.set()
                except Exception:
                    pass
            await self.emit(
                eid,
                {
                    "kind": "Event",
                    "content": {"phase": "preempted", "by": controller_id, "ts": int(time.time() * 1000)},
                },
            )

        elif op == "pause":
            run.state = RunState.PAUSED
            await self.emit(
                eid,
                {"kind": "Event", "content": {"phase": "paused", "by": controller_id, "ts": int(time.time() * 1000)}},
            )

        elif op == "resume":
            run.state = RunState.RUNNING
            await self.emit(
                eid,
                {"kind": "Event", "content": {"phase": "resumed", "by": controller_id, "ts": int(time.time() * 1000)}},
            )

        elif op == "set_budget":
            if "tokens" in content:
                run.budgets["tokens"] = content["tokens"]
            if "time_s" in content:
                run.budgets["time_s"] = content["time_s"]
            await self.emit(
                eid,
                {
                    "kind": "Event",
                    "content": {
                        "phase": "budget_updated",
                        "by": controller_id,
                        "budgets": run.budgets,
                        "ts": int(time.time() * 1000),
                    },
                },
            )
        else:
            await self.emit(
                eid,
                {
                    "kind": "Event",
                    "content": {
                        "phase": "control_noop",
                        "op": op,
                        "by": controller_id,
                        "noop": True,
                        "ts": int(time.time() * 1000),
                    },
                },
            )

    async def _fanout_loop(self, run: Run):
        # one loop per run; deliver messages to all sockets
        while True:
            ev = await run.fanout_q.get()
            if ev is None:
                break
            dead = []
            for role_set in run.conns.values():
                for ws in list(role_set):
                    try:
                        await ws.send_json(ev)
                    except Exception:
                        dead.append(ws)
            for ws in dead:
                for role_set in run.conns.values():
                    role_set.discard(ws)


registry = RunRegistry()
