# code/apps/core/management/commands/processors/scaffold_processor.py
from __future__ import annotations
import re
import textwrap
import pathlib
from django.core.management.base import BaseCommand, CommandError

REF_RE = re.compile(r"^(?P<ns>[a-z0-9_\-]+)/(?P<name>[a-z0-9_\-]+)@(?P<ver>[0-9]+)$")


class Command(BaseCommand):
    help = "Scaffold a container-first WS processor (FastAPI WebSocket /run + presigned PUT uploads)."

    def add_arguments(self, parser):
        parser.add_argument("--ref", required=True, help="ns/name@ver (e.g., llm/litellm@1)")
        parser.add_argument("--template", choices=["generic", "llm"], default="generic")
        parser.add_argument("--state", choices=["stateless", "stateful"], default="stateless")
        parser.add_argument("--secrets", default="", help="comma-separated secret names (e.g., OPENAI_API_KEY,FOO)")
        parser.add_argument("--cpu", default="1", help='CPU (string, e.g. "1")')
        parser.add_argument("--memory", type=int, default=2, help="Memory (GiB)")
        parser.add_argument("--timeout", type=int, default=600, help="Timeout seconds")
        parser.add_argument("--gpu", default="", help="GPU type (e.g., a10g) or empty")
        parser.add_argument("--port", type=int, default=8000, help="Container WS/HTTP port")
        parser.add_argument("--force", action="store_true", help="Overwrite existing files")

    def handle(self, *args, **opts):
        ref = opts["ref"]
        m = REF_RE.match(ref)
        if not m:
            raise CommandError("ref must match ns/name@ver (e.g., llm/litellm@1)")

        ns, name, ver = m.group("ns"), m.group("name"), int(m.group("ver"))
        slug = f"{ns}_{name}"
        proc_dir = pathlib.Path(f"apps/core/processors/{slug}")
        app_dir = proc_dir / "app"
        force = opts["force"]
        template = opts["template"]
        state = opts["state"]
        secrets = [s.strip() for s in (opts["secrets"] or "").split(",") if s.strip()]
        cpu, memory_gb, timeout_s, gpu = opts["cpu"], int(opts["memory"]), int(opts["timeout"]), (opts["gpu"] or None)
        port = int(opts["port"])

        if proc_dir.exists() and not force:
            raise CommandError(f"{proc_dir} already exists (use --force to overwrite).")

        proc_dir.mkdir(parents=True, exist_ok=True)
        app_dir.mkdir(parents=True, exist_ok=True)

        # Write files
        self._write(proc_dir / "Dockerfile", self._render_dockerfile(port, template))
        self._write(
            proc_dir / "registry.yaml",
            self._render_registry_yaml(ns, name, ver, cpu, memory_gb, timeout_s, gpu, secrets, template),
        )

        self._write(app_dir / "__init__.py", "")
        self._write(app_dir / "logging.py", LOGGING_PY)
        self._write(app_dir / "types.py", TYPES_PY)
        self._write(app_dir / "run_registry.py", RUN_REGISTRY_PY)
        self._write(app_dir / "uploader.py", UPLOADER_PY)
        self._write(app_dir / "handler.py", self._render_handler_py(template))
        self._write(app_dir / "ws.py", self._render_ws_py(port))

        if state == "stateful":
            self._write(app_dir / "state.py", STATEFUL_PY)
        else:
            self._write(app_dir / "state.py", "STATE = {}\n")

        self.stdout.write(self.style.SUCCESS(f"Scaffolded WS processor at {proc_dir}"))

    def _write(self, path: pathlib.Path, content: str):
        path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")

    # ------------------ Templates ------------------

    def _render_dockerfile(self, port: int, template: str) -> str:
        extra_pip = ""
        if template == "llm":
            extra_pip = ' \\\n    "litellm>=1.43.0"'
        return f"""
        FROM python:3.11-slim

        ENV PYTHONDONTWRITEBYTECODE=1 \\
            PYTHONUNBUFFERED=1 \\
            TZ=UTC \\
            LC_ALL=C.UTF-8

        RUN apt-get update && apt-get install -y --no-install-recommends \\
            curl ca-certificates build-essential gcc g++ \\
            && rm -rf /var/lib/apt/lists/*

        WORKDIR /work
        COPY app/ /work/app/

        RUN pip install --no-cache-dir \\
            "fastapi>=0.114" \\
            "uvicorn[standard]>=0.30" \\
            "pydantic>=2.8" \\
            "jsonschema>=4.22" \\
            "requests>=2.32"{extra_pip}

        # Make arbitrary UID runs safe (bind-mounts deletable by host user)
        RUN mkdir -p /artifacts /work /home/app && chmod -R 0777 /artifacts /work /home/app
        ENV HOME=/home/app XDG_CACHE_HOME=/home/app/.cache HF_HOME=/home/app/.cache/huggingface

        EXPOSE {port}
        CMD ["uvicorn", "app.ws:app", "--host", "0.0.0.0", "--port", "{port}"]

        HEALTHCHECK --interval=10s --timeout=3s --retries=5 \\
          CMD curl -sf http://localhost:{port}/healthz || exit 1
        """

    def _render_registry_yaml(
        self,
        ns: str,
        name: str,
        ver: int,
        cpu: str,
        memory_gb: int,
        timeout_s: int,
        gpu: str | None,
        secrets: list[str],
        template: str,
    ) -> str:
        if template == "llm":
            inputs_schema = {
                "$schema": "https://json-schema.org/draft-07/schema#",
                "title": f"{ns}/{name} inputs v1",
                "type": "object",
                "additionalProperties": False,
                "required": ["schema", "params"],
                "properties": {
                    "schema": {"const": "v1"},
                    "params": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["messages"],
                        "properties": {
                            "model": {"type": "string"},
                            "messages": {
                                "type": "array",
                                "minItems": 1,
                                "items": {
                                    "type": "object",
                                    "required": ["role", "content"],
                                    "properties": {
                                        "role": {"enum": ["user", "system", "assistant"]},
                                        "content": {"type": "string", "minLength": 1},
                                    },
                                },
                            },
                        },
                    },
                },
            }
            outputs = [
                {"path": "text/response.txt", "mime": "text/plain", "description": "LLM response"},
                {"path": "metadata.json", "mime": "application/json", "description": "Execution metadata"},
            ]
        else:
            inputs_schema = {
                "$schema": "https://json-schema.org/draft-07/schema#",
                "title": f"{ns}/{name} inputs v1",
                "type": "object",
                "additionalProperties": True,
            }
            outputs = [{"path": "metadata.json", "mime": "application/json", "description": "Execution metadata"}]

        yaml_obj = {
            "ref": f"{ns}/{name}@{ver}",
            "build": {"context": ".", "dockerfile": "Dockerfile", "port": 8000},
            "image": {
                "platforms": {
                    "amd64": f"ghcr.io/owner/repo/{ns}-{name}@sha256:REPLACE_AMD64",
                    "arm64": f"ghcr.io/owner/repo/{ns}-{name}@sha256:REPLACE_ARM64",
                },
            },
            "runtime": {
                "cpu": str(cpu),
                "memory_gb": int(memory_gb),
                "timeout_s": int(timeout_s),
                "gpu": (gpu or None),
            },
            "api": {"protocol": "ws", "path": "/run", "healthz": "/healthz"},
            "secrets": {"required": secrets},
            "inputs": inputs_schema,
            "outputs": outputs,
        }
        import yaml as _yaml

        return _yaml.dump(yaml_obj, sort_keys=False)

    def _render_handler_py(self, template: str) -> str:
        if template == "llm":
            body = """
            import os, io, json
            from typing import Any, Dict, Callable, Optional
            from .uploader import put_object, ensure_outputs_json

            # entry(payload, emit) -> envelope
            def entry(payload: Dict[str, Any], emit: Optional[Callable[[Dict], None]] = None) -> Dict[str, Any]:
                execution_id = str(payload.get("execution_id","")).strip()
                mode = str(payload.get("mode","mock")).strip()
                write_prefix = str(payload.get("write_prefix","")).strip()
                inputs = payload.get("inputs") or {}
                put_urls: Dict[str, str] = (payload.get("put_urls") or {})

                if not execution_id:
                    return {"status":"error","execution_id":"","error":{"code":"ERR_INPUTS","message":"missing execution_id"},"meta":{}}
                if "{execution_id}" in write_prefix:
                    write_prefix = write_prefix.replace("{execution_id}", execution_id)

                params = (inputs or {}).get("params") or {}
                messages = params.get("messages") or []
                model = params.get("model") or "gpt-4o-mini"

                if emit: emit({"kind":"Event","content":{"phase":"started"}})

                if mode == "mock":
                    text = f"Mock response: {messages[-1]['content'][:64] if messages else ''}"
                    if emit:
                        for chunk in text.split():
                            emit({"kind":"Token","content":{"text": chunk + " "}})
                else:
                    api_key = os.getenv("OPENAI_API_KEY")
                    if not api_key:
                        return {"status":"error","execution_id":execution_id,"error":{"code":"ERR_MISSING_SECRET","message":"OPENAI_API_KEY missing"},"meta":{}}
                    try:
                        import litellm
                        resp = litellm.completion(model=model, messages=messages, stream=True)
                        parts = []
                        for ev in resp:
                            delta = getattr(ev.choices[0].delta, "content", "") if hasattr(ev.choices[0], "delta") else ""
                            if delta:
                                parts.append(delta)
                                if emit: emit({"kind":"Token","content":{"text": delta}})
                        text = "".join(parts)
                    except Exception as e:
                        return {"status":"error","execution_id":execution_id,"error":{"code":"ERR_PROVIDER","message":str(e)},"meta":{}}

                image_digest = os.getenv("IMAGE_DIGEST")
                if not image_digest:
                    return {"status":"error","execution_id":execution_id,"error":{"code":"ERR_IMAGE_DIGEST_MISSING","message":"IMAGE_DIGEST not set"},"meta":{}}

                etags = {}
                reply_key = "outputs/text/response.txt"
                if reply_key not in put_urls:
                    return {"status":"error","execution_id":execution_id,"error":{"code":"ERR_UPLOAD_PLAN","message":f"missing put_url for {reply_key}"},"meta":{}}
                try:
                    etags[reply_key] = put_object(put_urls[reply_key], io.BytesIO(text.encode("utf-8")), content_type="text/plain")
                except Exception as e:
                    return {"status":"error","execution_id":execution_id,"error":{"code":"ERR_UPLOAD","message":f"Failed to upload {reply_key}: {str(e)}"},"meta":{}}

                # outputs.json LAST
                index_key = "outputs.json"
                outputs_list = [ {"path": f"{write_prefix}outputs/text/response.txt"} ]
                index_bytes = ensure_outputs_json(outputs_list)
                if index_key not in put_urls:
                    return {"status":"error","execution_id":execution_id,"error":{"code":"ERR_UPLOAD_PLAN","message":f"missing put_url for {index_key}"},"meta":{}}
                try:
                    etags[index_key] = put_object(put_urls[index_key], io.BytesIO(index_bytes), content_type="application/json")
                except Exception as e:
                    return {"status":"error","execution_id":execution_id,"error":{"code":"ERR_UPLOAD","message":f"Failed to upload {index_key}: {str(e)}"},"meta":{}}

                meta = {"env_fingerprint":"cpu:1;memory:2Gi","image_digest":image_digest,"model":model,"proof":{"etag_map":etags}}
                if emit: emit({"kind":"Event","content":{"phase":"completed"}})
                return {
                    "status":"success",
                    "execution_id": execution_id,
                    "outputs": outputs_list,
                    "index_path": f"{write_prefix}{index_key}",
                    "meta": meta
                }
            """
        else:
            body = """
            import os, io, json
            from typing import Any, Dict, Callable, Optional
            from .uploader import put_object, ensure_outputs_json

            def entry(payload: Dict[str, Any], emit: Optional[Callable[[Dict], None]] = None) -> Dict[str, Any]:
                execution_id = str(payload.get("execution_id","")).strip()
                mode = str(payload.get("mode","mock")).strip()
                write_prefix = str(payload.get("write_prefix","")).strip()
                inputs = payload.get("inputs") or {}
                put_urls: Dict[str, str] = (payload.get("put_urls") or {})

                if not execution_id:
                    return {"status":"error","execution_id":"","error":{"code":"ERR_INPUTS","message":"missing execution_id"},"meta":{}}
                if "{execution_id}" in write_prefix:
                    write_prefix = write_prefix.replace("{execution_id}", execution_id)

                image_digest = os.getenv("IMAGE_DIGEST")
                if not image_digest:
                    return {"status":"error","execution_id":execution_id,"error":{"code":"ERR_IMAGE_DIGEST_MISSING","message":"IMAGE_DIGEST not set"},"meta":{}}

                payload_json = json.dumps({"mode":mode,"inputs":inputs}, ensure_ascii=False)
                if emit:
                    emit({"kind":"Event","content":{"phase":"started"}})
                    emit({"kind":"Log","content":{"msg":"processing","bytes":len(payload_json)}})

                etags = {}
                meta_key = "outputs/metadata.json"
                if meta_key not in put_urls:
                    return {"status":"error","execution_id":execution_id,"error":{"code":"ERR_UPLOAD_PLAN","message":f"missing put_url for {meta_key}"},"meta":{}}
                try:
                    etags[meta_key] = put_object(put_urls[meta_key], io.BytesIO(payload_json.encode("utf-8")), content_type="application/json")
                except Exception as e:
                    return {"status":"error","execution_id":execution_id,"error":{"code":"ERR_UPLOAD","message":f"Failed to upload {meta_key}: {str(e)}"},"meta":{}}

                index_key = "outputs.json"
                outputs_list = [ {"path": f"{write_prefix}{meta_key}"} ]
                index_bytes = ensure_outputs_json(outputs_list)
                if index_key not in put_urls:
                    return {"status":"error","execution_id":execution_id,"error":{"code":"ERR_UPLOAD_PLAN","message":f"missing put_url for {index_key}"},"meta":{}}
                try:
                    etags[index_key] = put_object(put_urls[index_key], io.BytesIO(index_bytes), content_type="application/json")
                except Exception as e:
                    return {"status":"error","execution_id":execution_id,"error":{"code":"ERR_UPLOAD","message":f"Failed to upload {index_key}: {str(e)}"},"meta":{}}

                meta = {"env_fingerprint":"cpu:1;memory:2Gi","image_digest":image_digest,"proof":{"etag_map":etags}}
                if emit: emit({"kind":"Event","content":{"phase":"completed"}})
                return {
                    "status":"success",
                    "execution_id": execution_id,
                    "outputs": outputs_list,
                    "index_path": f"{write_prefix}{index_key}",
                    "meta": meta
                }
            """
        return f"""{body}"""

    def _render_ws_py(self, port: int) -> str:
        return """
        import asyncio, time, json, uuid
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
            connection_id = f"conn-{int(time.time()*1000)}"
            execution_id: Optional[str] = None
            role: Optional[ConnectionRole] = None

            try:
                # First frame must be RunOpen
                msg = await ws.receive_json()
                if not isinstance(msg, dict) or msg.get("kind") != "RunOpen":
                    await ws.close(code=1002); return
                content = msg.get("content") or {}
                role_s = str(content.get("role","")).lower()
                execution_id = str(content.get("execution_id","")).strip()
                payload = content.get("payload") or {}

                if role_s not in ("client","controller","observer") or not execution_id:
                    await ws.close(code=1008); return
                role = ConnectionRole[role_s.upper()]

                # TODO: verify ticket claims here (execution_id, scopes)

                # Register connection
                run = await registry.get_or_create(execution_id)
                await registry.add_connection(execution_id, connection_id, ws, role)
                await ws.send_json({"kind":"Ack","content":{"execution_id":execution_id}})

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
                        await registry.emit(execution_id, {"kind":"RunResult","content": env})
                        await ws.send_json({"kind":"RunResult","content": env})
                        info("ws.run.settle", execution_id=execution_id, status=env.get("status"), elapsed_ms=int((time.monotonic()-start)*1000))
                    except asyncio.CancelledError:
                        await registry.update_state(execution_id, RunState.PREEMPTED)
                        term = {"status":"error","execution_id":execution_id,"error":{"code":"ERR_PREEMPTED","message":"cancelled"}, "meta":{}}
                        await registry.emit(execution_id, {"kind":"RunResult","content": term})
                        await ws.send_json({"kind":"RunResult","content": term})
                    except Exception as e:
                        await registry.update_state(execution_id, RunState.ERROR)
                        term = {"status":"error","execution_id":execution_id,"error":{"code":"ERR_RUNTIME","message":str(e)}, "meta":{}}
                        await registry.emit(execution_id, {"kind":"RunResult","content": term})
                        await ws.send_json({"kind":"RunResult","content": term})

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
        """


# ---------------- Common tiny libs ----------------

LOGGING_PY = r"""
import json, os, sys, time
def _ts(): return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
def _stream(): return sys.stderr if (os.getenv("LOG_STREAM","stderr").lower()=="stderr") else sys.stdout
def info(event: str, **fields):
    rec = {"ts":_ts(),"level":"info","event":event,"service":"processor","env":os.getenv("APP_ENV", os.getenv("MODAL_ENVIRONMENT","dev"))}
    rec.update(fields)
    json.dump(rec, _stream(), separators=(",",":"), sort_keys=False); _stream().write("\n"); _stream().flush()
"""

TYPES_PY = r"""
from enum import Enum, auto

class ConnectionRole(Enum):
    CLIENT = auto()
    CONTROLLER = auto()
    OBSERVER = auto()

class RunState(Enum):
    PENDING = auto()
    RUNNING = auto()
    PAUSED = auto()
    PREEMPTED = auto()
    COMPLETED = auto()
    ERROR = auto()
"""

RUN_REGISTRY_PY = r"""
import asyncio, time
from typing import Dict, Set, Optional, Any
from .types import ConnectionRole, RunState
from .logging import info

class Run:
    __slots__ = ("eid","state","conns","budgets","fanout_q","fanout_task")
    def __init__(self, eid: str):
        self.eid = eid
        self.state = RunState.PENDING
        self.conns: Dict[ConnectionRole, Set[Any]] = {ConnectionRole.CLIENT:set(), ConnectionRole.CONTROLLER:set(), ConnectionRole.OBSERVER:set()}
        self.budgets = {"tokens": None, "time_s": None}
        self.fanout_q: asyncio.Queue = asyncio.Queue(maxsize=2048)
        self.fanout_task: Optional[asyncio.Task] = None

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

    async def add_connection(self, eid: str, cid: str, ws, role: ConnectionRole):
        run = await self.get_or_create(eid)
        run.conns[role].add(ws)
        info("ws.connect.ok", execution_id=eid, role=role.name.lower(), conns={r.name.lower(): len(s) for r,s in run.conns.items()})

    async def remove_connection(self, eid: str, cid: str):
        run = self._runs.get(eid)
        if not run: return
        for s in run.conns.values():
            s_copy = set(s)
            for ws in s_copy:
                if getattr(ws, "_cid", None) == cid:
                    s.remove(ws)
        info("ws.close", execution_id=eid, conns={r.name.lower(): len(s) for r,s in run.conns.items()})

    async def update_state(self, eid: str, state: RunState):
        run = await self.get_or_create(eid)
        run.state = state

    async def set_budget(self, eid: str, tokens=None, time_s=None):
        run = await self.get_or_create(eid)
        if tokens is not None: run.budgets["tokens"] = tokens
        if time_s is not None: run.budgets["time_s"] = time_s

    async def emit(self, eid: str, ev: dict):
        run = await self.get_or_create(eid)
        # backpressure: drop/squash only noisy token events if queue is full
        if run.fanout_q.full() and ev.get("kind") == "Token":
            return
        await run.fanout_q.put(ev)

    async def fanout_event(self, eid: str, ev: dict):
        await self.emit(eid, ev)

    async def maybe_gc_run(self, eid: str):
        run = self._runs.get(eid)
        if not run: return
        if all(len(s)==0 for s in run.conns.values()) and run.state in (RunState.COMPLETED, RunState.PREEMPTED, RunState.ERROR):
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
        if op == "preempt":
            await self._apply_preempt(eid, controller_id, content.get("reason","controller"))
        elif op == "pause":
            await self._apply_pause(eid, controller_id)
        elif op == "resume":
            await self._apply_resume(eid, controller_id)
        elif op == "set_budget":
            await self.set_budget(eid, tokens=content.get("tokens"), time_s=content.get("time_s"))
            await self.emit(eid, {"kind":"Event","content":{"phase":"budget_updated","by":controller_id,"budgets":(self._runs[eid].budgets if eid in self._runs else {}),"ts": int(time.time()*1000)}})
        else:
            await self.emit(eid, {"kind":"Event","content":{"phase":"control_noop","op":op,"by":controller_id,"noop":True,"ts":int(time.time()*1000)}})

    async def _apply_preempt(self, eid: str, controller_id: str, reason: str):
        run = await self.get_or_create(eid)
        if run.state in (RunState.PREEMPTED, RunState.COMPLETED, RunState.ERROR):
            await self.emit(eid, {"kind":"Event","content":{"phase":"preempted","by":controller_id,"reason":reason,"noop":True,"ts":int(time.time()*1000)}})
            return
        run.state = RunState.PREEMPTED
        # Cooperative cancel is handled in the entry runner (orchestrator cancels task)
        await self.emit(eid, {"kind":"Event","content":{"phase":"preempted","by":controller_id,"reason":reason,"ts":int(time.time()*1000)}})

    async def _apply_pause(self, eid: str, controller_id: str):
        run = await self.get_or_create(eid)
        run.state = RunState.PAUSED
        await self.emit(eid, {"kind":"Event","content":{"phase":"paused","by":controller_id,"ts":int(time.time()*1000)}})

    async def _apply_resume(self, eid: str, controller_id: str):
        run = await self.get_or_create(eid)
        run.state = RunState.RUNNING
        await self.emit(eid, {"kind":"Event","content":{"phase":"resumed","by":controller_id,"ts":int(time.time()*1000)}})

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
"""

UPLOADER_PY = r"""
import requests, json, io, time
from typing import List, Dict, Optional

_sess = requests.Session()

def put_object(put_url: str, fp: io.BytesIO, *, content_type: Optional[str] = None, retries: int = 3, timeout: int = 30) -> str:
    data = fp.getvalue()
    headers = {}
    if content_type:
        headers["Content-Type"] = content_type
    backoff = 0.2
    for i in range(retries):
        r = _sess.put(put_url, data=data, headers=headers, timeout=timeout)
        if 200 <= r.status_code < 300:
            return (r.headers.get("ETag") or "").strip('"')
        if r.status_code in (401, 403) and i < retries - 1:
            time.sleep(backoff); backoff *= 2
            continue
        r.raise_for_status()
    raise RuntimeError("unreachable")

def ensure_outputs_json(outputs: List[Dict]) -> bytes:
    outs = sorted(outputs, key=lambda o: o.get("path",""))
    return json.dumps({"outputs": outs}, ensure_ascii=False, separators=(",",":")).encode("utf-8")
"""

STATEFUL_PY = r"""
# Optional warmable cache for heavy state (models, tokenizers, etc.)
import threading
_lock = threading.Lock()
STATE = {"ready": False, "data": None}

def warm():
    STATE["ready"] = True
    STATE["data"] = {"note": "warmed"}

def get_state():
    if not STATE["ready"]:
        with _lock:
            if not STATE["ready"]:
                warm()
    return STATE
"""
