# code/apps/core/management/commands/scaffold_processor.py
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Tuple

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings


# -------------------------
# Utilities & Conventions
# -------------------------

REF_RX = re.compile(r"^(?P<ns>[a-z0-9][a-z0-9_-]*)/(?P<name>[a-z0-9][a-z0-9_-]*)@(?P<ver>[0-9]+)$")


@dataclass(frozen=True)
class Ref:
    ns: str
    name: str
    ver: int

    @property
    def display(self) -> str:
        return f"{self.ns}/{self.name}@{self.ver}"

    @property
    def slug(self) -> str:
        return f"{self.ns}_{self.name}"

    @classmethod
    def parse(cls, s: str) -> Ref:
        m = REF_RX.match(s.strip())
        if not m:
            raise CommandError("Invalid --ref. Expected ns/name@ver (e.g., llm/litellm@1).")
        return cls(ns=m.group("ns"), name=m.group("name"), ver=int(m.group("ver")))


def _root() -> Path:
    # repo/code
    p = Path(settings.BASE_DIR)  # backend.settings.* sets BASE_DIR=repo/code
    if p.name != "code":
        # Fallback: try to find code/ up the tree
        cand = Path.cwd()
        while cand != cand.parent:
            if (cand / "apps" / "core").exists():
                return cand
            cand = cand.parent
    return p


def _processor_dir(ref: Ref) -> Path:
    return _root() / "apps" / "core" / "processors" / ref.slug


def _app_dir(ref: Ref) -> Path:
    return _processor_dir(ref) / "app"


def _ensure_dirs(paths: Iterable[Path]) -> None:
    for p in paths:
        p.mkdir(parents=True, exist_ok=True)


def _fail_if_exists(paths: Iterable[Path]) -> List[Path]:
    exists = [p for p in paths if p.exists()]
    return exists


def _write(path: Path, content: str, *, overwrite: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        raise CommandError(f"Refusing to overwrite existing file without --force: {path}")
    path.write_text(content, encoding="utf-8")


def _fmt_cpu(cpu: str) -> str:
    cpu = cpu.strip()
    return cpu if cpu else "1"


def _fmt_mem_gb(mem: str | int) -> int:
    try:
        return int(mem)
    except Exception:
        return 2


def _fmt_timeout_s(t: str | int) -> int:
    try:
        return int(t)
    except Exception:
        return 600


def _comma_list(s: str | None) -> List[str]:
    if not s:
        return []
    return [x.strip() for x in s.split(",") if x.strip()]


# -------------------------
# Templates
# -------------------------

# NOTE: These strings use .format(); any literal braces in the generated files must be doubled { }.

DOCKERFILE_TPL = """\
# Generated processor Dockerfile for {ref_display}
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /work

# Minimal runtime deps; template may add more per type
RUN pip install --no-cache-dir fastapi==0.114.0 uvicorn==0.30.6 pydantic==2.9.2

# LLM template: include litellm
{maybe_llm_install}

# Copy only this processor directory
COPY app ./app

EXPOSE 8000

# Healthcheck: FastAPI /healthz
HEALTHCHECK --interval=10s --timeout=3s --retries=5 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz').read()"

CMD ["uvicorn", "app.http:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--log-level", "warning"]
"""

REGISTRY_YAML_TPL = """\
# Generated registry for {ref_display}
ref: {ref_display}

build:
  context: .
  dockerfile: ./Dockerfile
  target: null           # optional
  args: {{}}             # optional map of build-args
  platforms: [linux/amd64]   # default; override in CI if you do multi-arch

image:
  platforms:
    amd64: ghcr.io/owner/repo/{image_name}@sha256:REPLACE_ME_AMD64
    arm64: ghcr.io/owner/repo/{image_name}@sha256:REPLACE_ME_ARM64
  default_platform: amd64

runtime:
  cpu: "{cpu}"
  memory_gb: {memory_gb}
  timeout_s: {timeout_s}
  gpu: {gpu_null}

secrets:
  required: [{secrets_csv}]

inputs:
  $schema: "https://json-schema.org/draft-07/schema#"
  title: "{ref_display} inputs v1"
  type: object
  additionalProperties: false
  required: ["schema", "params"]
  properties:
    schema:
      const: "v1"
    params:
      type: object
      additionalProperties: false
      required: ["messages"]
      properties:
        model:
          type: string
          description: "Model name (for LLM template); optional"
        messages:
          type: array
          minItems: 1
          items:
            type: object
            required: ["role","content"]
            properties:
              role: {{ "enum": ["user","system","assistant"] }}
              content: {{ "type": "string", "minLength": 1 }}

outputs:
  - {{ path: "text/response.txt", mime: "text/plain", description: "LLM response" }}
  - {{ path: "metadata.json", mime: "application/json", description: "Execution metadata" }}
"""

APP_INIT_TPL = """\
# Generated package marker
"""

HTTP_PY_TPL = """\
from __future__ import annotations

import time
from json import JSONDecodeError
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from .handler import handle_run, handle_stream
from .logging import info, error
from .utils import error_envelope

app = FastAPI()


@app.get("/healthz")
async def healthz() -> dict:
    return {"ok": True}


@app.post("/run")
async def run(req: Request) -> JSONResponse:
    start = time.monotonic()
    try:
        # Defensive: check Content-Type
        content_type = req.headers.get("content-type", "").lower().split(";")[0]
        if content_type != "application/json":
            info("http.run.error", reason="unsupported_media_type")
            return JSONResponse(
                error_envelope("", "ERR_INPUTS", "Content-Type must be application/json", {"elapsed_ms": int((time.monotonic()-start)*1000)}),
                status_code=415
            )

        # Defensive: parse JSON body
        try:
            payload = await req.json()
        except JSONDecodeError:
            info("http.run.error", reason="invalid_json")
            info("http.run.settle", status="error", elapsed_ms=int((time.monotonic()-start)*1000))
            return JSONResponse(
                error_envelope("", "ERR_INPUTS", "Invalid JSON body", {"elapsed_ms": int((time.monotonic()-start)*1000)}),
                status_code=400
            )

        execution_id = str(payload.get("execution_id", "")).strip()
        if not execution_id:
            info("http.run.reject", reason="missing_execution_id")
            info("http.run.settle", status="error", elapsed_ms=int((time.monotonic()-start)*1000))
            return JSONResponse(
                error_envelope("", "ERR_INPUTS", "missing execution_id", {"elapsed_ms": int((time.monotonic()-start)*1000)}),
                status_code=400
            )

        info("http.run.start", execution_id=execution_id)
        env = await handle_run(payload)
        info("http.run.settle", execution_id=execution_id, status=env.get("status"), elapsed_ms=int((time.monotonic()-start)*1000))
        return JSONResponse(env)

    except Exception as e:
        error("http.run.error", reason="unhandled", err=str(e)[:500])
        info("http.run.settle", status="error", elapsed_ms=int((time.monotonic()-start)*1000))
        return JSONResponse(
            error_envelope("", "ERR_ADAPTER_INVOCATION", "internal_error", {"elapsed_ms": int((time.monotonic()-start)*1000)}),
            status_code=500
        )


@app.post("/run-stream")
async def run_stream(req: Request):
    payload = await req.json()
    execution_id = str(payload.get("execution_id", "")).strip()

    if not execution_id:
        info("http.stream.reject", reason="missing_execution_id")
        return JSONResponse(
            {"status": "error", "execution_id": "", "error": {"code": "ERR_INPUTS", "message": "missing execution_id"}},
            status_code=400
        )

    info("http.stream.start", execution_id=execution_id)

    async def gen():
        seq = 0
        try:
            async for evt in handle_stream(payload):
                seq += 1
                info("http.stream.chunk", execution_id=execution_id, seq=seq, bytes=len(str(evt)))
                yield f"data: {evt}\\n\\n"
            info("http.stream.end", execution_id=execution_id, total_chunks=seq)
        except Exception as e:
            info("http.stream.error", execution_id=execution_id, error=str(e))
            yield f"data: {{'event':'error','message':'{str(e)}'}}\\n\\n"
        finally:
            info("http.stream.settle", execution_id=execution_id, total_chunks=seq)

    return StreamingResponse(gen(), media_type="text/event-stream")
"""

LOGGING_PY_TPL = """\
from __future__ import annotations
import json
import os
import sys
import time
from typing import Any, Dict

def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def _stream():
    return sys.stderr

def log(level: str, event: str, **fields):
    base = {
        "ts": _ts(),
        "level": level,
        "event": event,
        "service": os.getenv("SERVICE","processor"),
        "env": os.getenv("APP_ENV", "dev"),
    }
    base.update(fields or {})
    json.dump(base, _stream(), separators=(",",":"), sort_keys=True)
    _stream().write("\\n")
    _stream().flush()

def info(event: str, **fields): log("info", event, **fields)
def warn(event: str, **fields): log("warn", event, **fields)
def error(event: str, **fields): log("error", event, **fields)
"""

UTILS_PY_TPL = """\
from __future__ import annotations
import hashlib
import json
from typing import Any, Dict

def env_fingerprint() -> str:
    # minimal/portable; expand later
    parts = ["cpu:1","memory:2Gi"]
    return ";".join(parts)

def success_envelope(execution_id: str, outputs: list, index_path: str, meta: dict) -> dict:
    return {
        "status":"success",
        "execution_id": execution_id,
        "outputs": outputs,
        "index_path": index_path,
        "meta": meta,
    }

def error_envelope(execution_id: str, code: str, message: str, meta: dict) -> dict:
    return {
        "status":"error",
        "execution_id": execution_id,
        "error": {"code": code, "message": message},
        "meta": meta,
    }
"""

HANDLER_GENERIC_TPL = """\
from __future__ import annotations
import os
from typing import Any, Dict, AsyncGenerator

from .logging import info, error
from .utils import env_fingerprint, success_envelope, error_envelope

# Generic template: echo back something deterministic

async def handle_run(payload: Dict[str, Any]) -> Dict[str, Any]:
    eid = str(payload.get("execution_id","")).strip()
    if not eid:
        return error_envelope("", "ERR_INPUTS", "missing execution_id", {"env_fingerprint": env_fingerprint()})

    write_prefix = str(payload.get("write_prefix","")).strip().replace("{execution_id}", eid)
    # minimal fake output
    outputs = [{"path": f"{write_prefix}outputs/response.txt"}]
    index_path = f"{write_prefix}outputs.json"
    meta = {
        "env_fingerprint": env_fingerprint(),
        "image_digest": os.getenv("IMAGE_DIGEST", "unknown")
    }
    info("handler.generic.ok", execution_id=eid, write_prefix=write_prefix)
    return success_envelope(eid, outputs, index_path, meta)

async def handle_stream(payload: Dict[str, Any]) -> AsyncGenerator[str, None]:
    # trivial 3-step stream
    yield '{"event":"start"}'
    yield '{"event":"progress","pct":50}'
    yield '{"event":"done"}'
"""

HANDLER_LLM_TPL = """\
from __future__ import annotations
import os
from typing import Any, Dict, AsyncGenerator

from .logging import info, error
from .utils import env_fingerprint, success_envelope, error_envelope

# LiteLLM is optional at import time to keep cold starts small until used
try:
    import litellm
except Exception:
    litellm = None

def _need_secret() -> str | None:
    return os.environ.get("OPENAI_API_KEY")

async def handle_run(payload: Dict[str, Any]) -> Dict[str, Any]:
    eid = str(payload.get("execution_id","")).strip()
    if not eid:
        return error_envelope("", "ERR_INPUTS", "missing execution_id", {"env_fingerprint": env_fingerprint()})

    mode = str(payload.get("mode","mock")).strip()
    p = dict(payload.get("inputs") or {})
    params = dict(p.get("params") or {})
    messages = list(params.get("messages") or [])
    model = str(params.get("model") or "gpt-4o-mini")

    write_prefix = str(payload.get("write_prefix","")).strip().replace("{execution_id}", eid)

    if mode == "mock":
        text = f"Mock response: {messages[-1]['content'] if messages else '…'}"
    else:
        if litellm is None:
            return error_envelope(eid, "ERR_RUNTIME", "litellm not installed in image", {"env_fingerprint": env_fingerprint()})
        if not _need_secret():
            return error_envelope(eid, "ERR_MISSING_SECRET", "OPENAI_API_KEY required in real mode", {"env_fingerprint": env_fingerprint()})
        try:
            resp = litellm.completion(model=model, messages=messages)
            # Normalize to text
            text = resp.choices[0].message.get("content") if hasattr(resp, "choices") else str(resp)
        except Exception as e:
            return error_envelope(eid, "ERR_PROVIDER", f"{type(e).__name__}: {e}", {"env_fingerprint": env_fingerprint()})

    # Strict digest validation
    image_digest = os.environ.get("IMAGE_DIGEST")
    if not image_digest:
        return error_envelope(
            eid,
            "ERR_IMAGE_DIGEST_MISSING",
            "IMAGE_DIGEST env var not set",
            {"env_fingerprint": env_fingerprint()}
        )

    # Minimal "write": adapters own storage, but we return canonical paths
    outputs = [{"path": f"{write_prefix}outputs/response.txt"}]
    index_path = f"{write_prefix}outputs.json"
    meta = {
        "env_fingerprint": env_fingerprint(),
        "model": model,
        "image_digest": image_digest,
    }
    info("handler.llm.ok", execution_id=eid, write_prefix=write_prefix)
    return success_envelope(eid, outputs, index_path, meta)

async def handle_stream(payload: Dict[str, Any]) -> AsyncGenerator[str, None]:
    # For now, simple staged events. Replace with token streaming if needed.
    yield '{"event":"start"}'
    yield '{"event":"progress","pct":33}'
    yield '{"event":"progress","pct":66}'
    yield '{"event":"done"}'
"""


# -------------------------
# Command
# -------------------------


class Command(BaseCommand):
    help = "Scaffold a new HTTP-based processor (FastAPI): Dockerfile, registry.yaml, and app/*"

    def add_arguments(self, parser):
        parser.add_argument("--ref", required=True, help="ns/name@ver (e.g., llm/litellm@1)")
        parser.add_argument("--template", choices=["generic", "llm", "image"], default="generic")
        parser.add_argument("--secrets", help="Comma-separated secret names (e.g. OPENAI_API_KEY,HF_TOKEN)")
        parser.add_argument("--cpu", default="1")
        parser.add_argument("--memory", default="2", help="GB")
        parser.add_argument("--timeout", default="600", help="seconds")
        parser.add_argument("--gpu", default=None)
        parser.add_argument("--force", action="store_true", help="Overwrite existing files")

    def handle(self, *args, **opts):
        ref = Ref.parse(opts["ref"])
        template = opts["template"]
        secrets = _comma_list(opts.get("secrets"))
        cpu = _fmt_cpu(opts.get("cpu", "1"))
        memory_gb = _fmt_mem_gb(opts.get("memory", 2))
        timeout_s = _fmt_timeout_s(opts.get("timeout", 600))
        gpu = opts.get("gpu")
        force = bool(opts.get("force"))

        proc_dir = _processor_dir(ref)
        app_dir = _app_dir(ref)

        files = [
            proc_dir / "Dockerfile",
            proc_dir / "registry.yaml",
            app_dir / "__init__.py",
            app_dir / "http.py",
            app_dir / "handler.py",
            app_dir / "logging.py",
            app_dir / "utils.py",
        ]

        # Preflight: refuse overwrite unless --force
        exists = _fail_if_exists(files)
        if exists and not force:
            lines = "\n  ".join(str(p) for p in exists)
            raise CommandError(f"Files already exist. Re-run with --force to overwrite:\n  {lines}")

        # Render templates
        maybe_llm_install = "RUN pip install --no-cache-dir litellm==1.43.6" if template == "llm" else ""
        image_name = f"{ref.ns}-{ref.name}"

        secrets_csv = ", ".join(secrets) if secrets else ""
        gpu_null = "null" if not gpu else f'"{gpu}"'

        dockerfile = DOCKERFILE_TPL.format(
            ref_display=ref.display,
            maybe_llm_install=maybe_llm_install,
        )

        registry_yaml = REGISTRY_YAML_TPL.format(
            ref_display=ref.display,
            image_name=image_name,
            cpu=cpu,
            memory_gb=memory_gb,
            timeout_s=timeout_s,
            gpu_null=gpu_null,
            secrets_csv=secrets_csv,
        )

        http_py = HTTP_PY_TPL
        logging_py = LOGGING_PY_TPL
        utils_py = UTILS_PY_TPL
        app_init = APP_INIT_TPL

        if template == "llm":
            handler_py = HANDLER_LLM_TPL
        else:
            handler_py = HANDLER_GENERIC_TPL

        # Write
        _ensure_dirs([proc_dir, app_dir])
        _write(proc_dir / "Dockerfile", dockerfile, overwrite=force)
        _write(proc_dir / "registry.yaml", registry_yaml, overwrite=force)
        _write(app_dir / "__init__.py", app_init, overwrite=force)
        _write(app_dir / "http.py", http_py, overwrite=force)
        _write(app_dir / "handler.py", handler_py, overwrite=force)
        _write(app_dir / "logging.py", logging_py, overwrite=force)
        _write(app_dir / "utils.py", utils_py, overwrite=force)

        created = [str(p.relative_to(_root())) for p in files]
        self.stdout.write(self.style.SUCCESS(f"Scaffolded processor: {ref.display}"))
        for r in created:
            self.stdout.write(f"  - {r}")

        # Next steps (explicit, concise)
        self.stdout.write("\nNext steps:")
        self.stdout.write("  1) Commit & push these files.")
        self.stdout.write(
            f"  2) Build the image: docker build -t {ref.ns}-{ref.name}:dev apps/core/processors/{ref.slug}"
        )
        self.stdout.write("  3) Buildx multi-arch & push to GHCR, then pin digests into registry.yaml.")
        if secrets:
            pretty = ", ".join(secrets)
            self.stdout.write(f"  4) Configure Modal secrets: {pretty}.")
            step = 5
        else:
            step = 4
        self.stdout.write(f"  {step}) Deploy with digest and run smoke via run_processor --adapter modal --mode mock.")
