# Separate process that executes entry(...) and relays events over IPC.
from __future__ import annotations
import os, sys, traceback
from typing import Any, Dict, Callable
from multiprocessing import get_context

# Local imports are safe here (we run inside the container)
from .handler import entry

def _emit_to_q(q):
    def _emit(ev: Dict[str, Any]):
        # Defensive: ensure small JSON-able dicts (large media goes via PUT)
        if isinstance(ev, dict) and "kind" in ev:
            q.put(ev)
    return _emit

def _run(payload: Dict[str, Any], q, cancel_ev):
    try:
        env = entry(payload, emit=_emit_to_q(q), ctrl=cancel_ev)
        q.put({"kind":"RunResult","content": env})
    except Exception as e:
        # Never raise; always finalize with error envelope
        run_id = str(payload.get("run_id") or payload.get("execution_id", ""))
        q.put({"kind":"RunResult","content":{
            "status":"error",
            "run_id": run_id,
            "error": {"code":"ERR_RUNTIME","message": f"{type(e).__name__}: {e}"},
            "meta": {}
        }})

def spawn_worker(payload: Dict[str, Any]):
    mp = get_context("spawn")
    q = mp.Queue(maxsize=2048)
    cancel_ev = mp.Event()
    proc = mp.Process(target=_run, args=(payload, q, cancel_ev), daemon=True)
    proc.start()
    return proc, q, cancel_ev
