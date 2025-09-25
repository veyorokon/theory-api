import time
import json
from json import JSONDecodeError
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
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

    # Return appropriate HTTP status codes based on error type
    if env.get("status") == "error":
        error_code = env.get("error", {}).get("code", "")
        if error_code == "ERR_INPUTS":
            return JSONResponse(env, status_code=400)
        elif error_code in ["ERR_IMAGE_DIGEST_MISSING", "ERR_RUNTIME", "ERR_PROVIDER"]:
            return JSONResponse(env, status_code=500)
        else:
            return JSONResponse(env, status_code=500)  # Default to 500 for unknown errors

    return JSONResponse(env)


@app.post("/run-stream")
async def run_stream(req: Request) -> StreamingResponse:
    """Streaming version of /run endpoint using Server-Sent Events."""
    start = time.monotonic()
    ct = (req.headers.get("content-type") or "").lower().split(";")[0]

    def error_stream(eid: str, code: str, msg: str):
        """Stream an error event."""
        error_env = _err(eid, code, msg)
        yield "event: error\n"
        yield f"data: {json.dumps(error_env)}\n\n"

    if ct != "application/json":
        info("http.run_stream.error", reason="unsupported_media_type")
        return StreamingResponse(
            error_stream("", "ERR_INPUTS", "Content-Type must be application/json"),
            media_type="text/event-stream",
            status_code=415,
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    try:
        payload = await req.json()
    except JSONDecodeError:
        info("http.run_stream.error", reason="invalid_json")
        return StreamingResponse(
            error_stream("", "ERR_INPUTS", "Invalid JSON body"),
            media_type="text/event-stream",
            status_code=400,
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    eid = str(payload.get("execution_id", "")).strip()
    if not eid:
        return StreamingResponse(
            error_stream("", "ERR_INPUTS", "missing execution_id"),
            media_type="text/event-stream",
            status_code=400,
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    def event_generator():
        """Generate SSE events for the streaming response."""
        info("http.run_stream.start", execution_id=eid)

        # Emit progress event
        yield "event: progress\n"
        yield f"data: {json.dumps({'execution_id': eid, 'status': 'processing'})}\n\n"

        # Execute the handler
        env = entry(payload)

        info(
            "http.run_stream.settle",
            execution_id=eid,
            status=env.get("status"),
            elapsed_ms=int((time.monotonic() - start) * 1000),
        )

        # Emit final done event with complete envelope
        yield "event: done\n"
        yield f"data: {json.dumps(env)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
