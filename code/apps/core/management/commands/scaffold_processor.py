# code/apps/core/management/commands/processors/scaffold_processor.py
from __future__ import annotations
import re
import textwrap
import pathlib
from django.core.management.base import BaseCommand, CommandError

REF_RE = re.compile(r"^(?P<ns>[a-z0-9_\-]+)/(?P<name>[a-z0-9_\-]+)@(?P<ver>[0-9]+)$")


class Command(BaseCommand):
    help = "Scaffold a container-first HTTP processor (FastAPI /run)."

    def add_arguments(self, parser):
        parser.add_argument("--ref", required=True, help="ns/name@ver (e.g., llm/litellm@1)")
        parser.add_argument("--template", choices=["generic", "llm"], default="generic")
        parser.add_argument("--state", choices=["stateless", "stateful"], default="stateless")
        parser.add_argument("--secrets", default="", help="comma-separated secret names (e.g., OPENAI_API_KEY,FOO)")
        parser.add_argument("--cpu", default="1", help='CPU (string, e.g. "1")')
        parser.add_argument("--memory", type=int, default=2, help="Memory (GiB)")
        parser.add_argument("--timeout", type=int, default=600, help="Timeout seconds")
        parser.add_argument("--gpu", default="", help="GPU type (e.g., a10g) or empty")
        parser.add_argument("--port", type=int, default=8000, help="Container HTTP port")
        parser.add_argument("--with-stream", action="store_true", help="Also scaffold /run-stream SSE")
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
        with_stream = bool(opts["with_stream"])

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
        self._write(app_dir / "receipts.py", RECEIPTS_PY)
        self._write(app_dir / "handler.py", self._render_handler_py(template))
        self._write(app_dir / "http.py", self._render_http_py(port, with_stream))

        if state == "stateful":
            self._write(app_dir / "state.py", self._render_state_py(template))
        else:
            # Empty placeholder to keep imports safe if someone flips later
            self._write(app_dir / "state.py", "STATE = {}\n")

        self.stdout.write(self.style.SUCCESS(f"Scaffolded processor at {proc_dir}"))

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
            PYTHONUNBUFFERED=1

        RUN apt-get update && apt-get install -y --no-install-recommends \\
            curl \\
            ca-certificates \\
            build-essential \\
            gcc \\
            g++ \\
            && rm -rf /var/lib/apt/lists/*

        WORKDIR /work
        COPY app/ /work/app/

        RUN pip install --no-cache-dir \\
            "fastapi>=0.114" \\
            "uvicorn[standard]>=0.30" \\
            "pydantic>=2.8" \\
            "jsonschema>=4.22"{extra_pip}


        EXPOSE {port}
        # NOTE: We do NOT run uvicorn when used with Modal @asgi_app(); but for local docker run, this CMD is handy.
        CMD ["uvicorn", "app.http:app", "--host", "0.0.0.0", "--port", "{port}"]

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
        # Minimal JSON Schema tailored per template (can extend later)
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
        else:
            inputs_schema = {
                "$schema": "https://json-schema.org/draft-07/schema#",
                "title": f"{ns}/{name} inputs v1",
                "type": "object",
                "additionalProperties": True,
            }

        outputs = [{"path": "metadata.json", "mime": "application/json", "description": "Execution metadata"}]
        if template == "llm":
            outputs.insert(0, {"path": "text/response.txt", "mime": "text/plain", "description": "LLM response"})

        yaml = {
            "ref": f"{ns}/{name}@{ver}",
            "build": {"context": ".", "dockerfile": "Dockerfile", "port": 8000},
            "image": {
                "platforms": {
                    "amd64": f"ghcr.io/owner/repo/{ns}-{name}@sha256:REPLACE_AMD64",
                    "arm64": f"ghcr.io/owner/repo/{ns}-{name}@sha256:REPLACE_ARM64",
                },
                "default_platform": "amd64",
            },
            "runtime": {
                "cpu": str(cpu),
                "memory_gb": int(memory_gb),
                "timeout_s": int(timeout_s),
                "gpu": (gpu or None),
            },
            "secrets": {"required": secrets},
            "inputs": inputs_schema,
            "outputs": outputs,
        }
        import yaml as _yaml  # pyyaml is already in your project; if not, change to json.dumps

        return _yaml.dump(yaml, sort_keys=False)

    def _render_handler_py(self, template: str) -> str:
        # LLM template mock/real; generic just echoes inputs
        if template == "llm":
            body = """
            import os
            from typing import Any, Dict, List
            from .receipts import write_outputs_and_receipts
            from .logging import info

            def entry(payload: Dict[str, Any]) -> Dict[str, Any]:
                # Basic shape checks (envelope-level)
                execution_id = str(payload.get("execution_id", "")).strip()
                mode = str(payload.get("mode", "mock")).strip()
                write_prefix = str(payload.get("write_prefix", "")).strip()
                inputs = payload.get("inputs") or {}

                if not execution_id:
                    return {"status":"error","execution_id":"","error":{"code":"ERR_INPUTS","message":"missing execution_id"},"meta":{}}
                if "{execution_id}" in write_prefix:
                    write_prefix = write_prefix.replace("{execution_id}", execution_id)

                params = (inputs or {}).get("params") or {}
                messages: List[Dict[str, str]] = params.get("messages") or []
                model = params.get("model") or "gpt-4o-mini"

                # Mock path is hermetic (no secrets)
                if mode == "mock":
                    text = f"Mock response: {messages[-1]['content'][:64] if messages else ''}"
                else:
                    # Real path: secrets required
                    api_key = os.environ.get("OPENAI_API_KEY")
                    if not api_key:
                        return {"status":"error","execution_id":execution_id,"error":{"code":"ERR_MISSING_SECRET","message":"OPENAI_API_KEY missing"},"meta":{}}

                    # Lazy import with defensive fallback
                    try:
                        import litellm
                        resp = litellm.completion(model=model, messages=messages)
                        text = resp.choices[0].message.get("content") if hasattr(resp, "choices") else str(resp)
                    except ImportError:
                        return {"status":"error","execution_id":execution_id,"error":{"code":"ERR_RUNTIME","message":"litellm not installed in image"},"meta":{}}
                    except Exception as e:
                        return {"status":"error","execution_id":execution_id,"error":{"code":"ERR_PROVIDER","message":f"{type(e).__name__}: {e}"},"meta":{}}

                # Strict digest validation
                image_digest = os.environ.get("IMAGE_DIGEST")
                if not image_digest:
                    return {"status":"error","execution_id":execution_id,"error":{"code":"ERR_IMAGE_DIGEST_MISSING","message":"IMAGE_DIGEST env var not set"},"meta":{}}

                meta = {
                    "env_fingerprint": f"cpu:1;memory:2Gi",
                    "model": model,
                    "image_digest": image_digest
                }

                info("handler.llm.ok", execution_id=execution_id, write_prefix=write_prefix)
                return write_outputs_and_receipts(
                    execution_id=execution_id,
                    write_prefix=write_prefix,
                    meta=meta,
                    outputs=[("text/response.txt", text)]
                )
            """
        else:
            body = """
            from typing import Any, Dict
            from .receipts import write_outputs_and_receipts
            from .logging import info

            def entry(payload: Dict[str, Any]) -> Dict[str, Any]:
                execution_id = str(payload.get("execution_id", "")).strip()
                mode = str(payload.get("mode", "mock")).strip()
                write_prefix = str(payload.get("write_prefix", "")).strip()
                inputs = payload.get("inputs") or {}

                if not execution_id:
                    return {"status":"error","execution_id":"","error":{"code":"ERR_INPUTS","message":"missing execution_id"},"meta":{}}
                if "{execution_id}" in write_prefix:
                    write_prefix = write_prefix.replace("{execution_id}", execution_id)

                # Strict digest validation
                image_digest = os.environ.get("IMAGE_DIGEST")
                if not image_digest:
                    return {"status":"error","execution_id":execution_id,"error":{"code":"ERR_IMAGE_DIGEST_MISSING","message":"IMAGE_DIGEST env var not set"},"meta":{}}

                # Echo implementation (mock/real both allowed, no secrets)
                meta = {
                    "env_fingerprint": "cpu:1;memory:2Gi",
                    "image_digest": image_digest
                }
                text = f"ok mode={mode} inputs={inputs!r}"

                info("handler.generic.ok", execution_id=execution_id, write_prefix=write_prefix)
                return write_outputs_and_receipts(
                    execution_id=execution_id,
                    write_prefix=write_prefix,
                    meta=meta,
                    outputs=[("metadata.json", text)]
                )
            """
        return f"""
        {body}
        """

    def _render_http_py(self, port: int, with_stream: bool) -> str:
        stream_block = ""
        if with_stream:
            stream_block = """
            from fastapi import BackgroundTasks
            from fastapi.responses import StreamingResponse

            @app.post("/run-stream")
            async def run_stream(req: Request, background: BackgroundTasks):
                # Same guards as /run for content-type and JSON
                ct = (req.headers.get("content-type") or "").lower().split(";")[0]
                if ct != "application/json":
                    info("http.run.error", reason="unsupported_media_type")
                    return JSONResponse(_err("", "ERR_INPUTS", "Content-Type must be application/json"), status_code=415)
                try:
                    payload = await req.json()
                except Exception:
                    info("http.run.error", reason="invalid_json")
                    return JSONResponse(_err("", "ERR_INPUTS", "Invalid JSON body"), status_code=400)

                eid = str(payload.get("execution_id","")).strip()
                if not eid:
                    return JSONResponse(_err("", "ERR_INPUTS", "missing execution_id"), status_code=400)

                info("http.stream.start", execution_id=eid)

                def gen():
                    import time, json as _json
                    for i in range(3):
                        time.sleep(0.25)
                        yield f"data: " + _json.dumps({"event":"tick","i":i,"execution_id":eid}) + "\\n\\n"
                    # Final envelope
                    env = entry(payload)
                    yield "data: " + json.dumps(env) + "\\n\\n"

                return StreamingResponse(gen(), media_type="text/event-stream")
            """

        return f"""
        import json, time
        from json import JSONDecodeError
        from fastapi import FastAPI, Request
        from fastapi.responses import JSONResponse
        from .handler import entry
        from .logging import info

        app = FastAPI()

        @app.get("/healthz")
        def healthz():
            return {{"ok": True}}

        def _err(eid: str, code: str, msg: str):
            return {{"status":"error","execution_id":eid,"error":{{"code":code,"message":msg}},"meta":{{}}}}

        @app.post("/run")
        async def run(req: Request) -> JSONResponse:
            start = time.monotonic()
            ct = (req.headers.get("content-type") or "").lower().split(";")[0]
            if ct != "application/json":
                info("http.run.error", reason="unsupported_media_type")
                return JSONResponse(_err("", "ERR_INPUTS", "Content-Type must be application/json"), status_code=415)
            try:
                payload = await req.json()
            except JSONDecodeError:
                info("http.run.error", reason="invalid_json")
                return JSONResponse(_err("", "ERR_INPUTS", "Invalid JSON body"), status_code=400)

            eid = str(payload.get("execution_id","")).strip()
            if not eid:
                return JSONResponse(_err("", "ERR_INPUTS", "missing execution_id"), status_code=400)

            info("http.run.start", execution_id=eid)
            env = entry(payload)
            info("http.run.settle", execution_id=eid, status=env.get("status"), elapsed_ms=int((time.monotonic()-start)*1000))
            return JSONResponse(env)

        {stream_block}
        """

    def _render_state_py(self, template: str) -> str:
        # A tiny, safe place to hold/prepare heavy state (import-once).
        # Works locally and under Modal snapshots (Modal config is on the deployment side).
        return """
        # Optional stateful module for heavy resources (models, tokenizers, etc.).
        # Keep imports local inside functions to avoid forcing deps at build time.
        # Expose a single get_state() so handler can use it when mode="real".
        import threading
        _lock = threading.Lock()
        STATE = { "ready": False, "data": None }

        def warm():
            # Put heavy init here (e.g., HF model load). Called lazily.
            # Keep this fast; rely on Modal snapshots to preserve loaded state between runs.
            STATE["ready"] = True
            STATE["data"] = {"note": "warmed"}

        def get_state():
            if not STATE["ready"]:
                with _lock:
                    if not STATE["ready"]:
                        warm()
            return STATE
        """


# ---------------- Common tiny libs (no external deps) ----------------

LOGGING_PY = r"""
import json, os, sys, time
def _ts(): return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
def _stream(): return sys.stderr if (os.getenv("LOG_STREAM","stderr").lower()=="stderr") else sys.stdout
def info(event: str, **fields):
    rec = {"ts":_ts(),"level":"info","event":event,"service":"processor","env":os.getenv("APP_ENV", os.getenv("MODAL_ENVIRONMENT","dev"))}
    rec.update(fields)
    json.dump(rec, _stream(), separators=(",",":"), sort_keys=False); _stream().write("\n"); _stream().flush()
"""

RECEIPTS_PY = r"""
import json, os, pathlib
from typing import Dict, List, Tuple

def _ensure_dir(p: str): pathlib.Path(p).mkdir(parents=True, exist_ok=True)

def write_outputs_and_receipts(
    execution_id: str,
    write_prefix: str,
    meta: Dict,
    outputs: List[Tuple[str, str]],   # [(relpath, text_content)]
) -> Dict:
    # Normalize write_prefix
    if "{execution_id}" in write_prefix:
        write_prefix = write_prefix.replace("{execution_id}", execution_id)
    if not write_prefix.endswith("/"):
        write_prefix += "/"

    out_dir = os.path.join(write_prefix, "outputs")
    _ensure_dir(out_dir)

    # Write payload outputs
    rel_paths = []
    for rel, content in outputs:
        abs_path = os.path.join(out_dir, rel)
        pathlib.Path(os.path.dirname(abs_path)).mkdir(parents=True, exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)
        rel_paths.append(os.path.join(write_prefix, "outputs", rel))

    # Write outputs index
    index_path = os.path.join(write_prefix, "outputs.json")
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump({"outputs":[{"path": p} for p in rel_paths]}, f, indent=2)

    # Dual receipts (identical)
    receipt = {
        "execution_id": execution_id,
        "index_path": index_path,
        "meta": meta,
    }
    # Local receipt
    with open(os.path.join(write_prefix, "receipt.json"), "w", encoding="utf-8") as f:
        json.dump(receipt, f, indent=2)
    # Global determinism receipt (use write_prefix, not hardcoded /artifacts)
    global_det = os.path.join(write_prefix, "determinism.json")
    with open(global_det, "w", encoding="utf-8") as f:
        json.dump(receipt, f, indent=2)

    return {
        "status": "success",
        "execution_id": execution_id,
        "outputs": [{"path": p} for p in rel_paths],
        "index_path": index_path,
        "meta": meta,
    }
"""
