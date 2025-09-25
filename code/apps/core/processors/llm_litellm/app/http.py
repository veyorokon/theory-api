import json
import time
from json import JSONDecodeError
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from .handler import entry
from .logging import info

app = FastAPI()


@app.get("/healthz")
def healthz():
    return {"ok": True}


def _err(eid: str, code: str, msg: str):
    return {"status": "error", "execution_id": eid, "error": {"code": code, "message": msg}, "meta": {}}


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

    eid = str(payload.get("execution_id", "")).strip()
    if not eid:
        return JSONResponse(_err("", "ERR_INPUTS", "missing execution_id"), status_code=400)

    info("http.run.start", execution_id=eid)
    env = entry(payload)
    info(
        "http.run.settle", execution_id=eid, status=env.get("status"), elapsed_ms=int((time.monotonic() - start) * 1000)
    )
    return JSONResponse(env)
