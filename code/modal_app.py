# modal_app.py
from __future__ import annotations

import io
import json
import os
import tarfile
import tempfile
import uuid
import subprocess
from pathlib import Path
from typing import Iterable, List

import modal


# -------------------------------
# Small utilities (pure helpers)
# -------------------------------


def _log(event: str, **fields):
    # Minimal structured logging to stdout
    payload = {"event": event, **fields}
    try:
        print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
    except Exception:
        print(f"[{event}] {fields!r}")


def _parse_tool_secrets(env_value: str | None) -> List[str]:
    if not env_value:
        return []
    return [s.strip() for s in env_value.split(",") if s.strip()]


def _pkg_from_ref(ref: str) -> str:
    """
    Convert 'ns/name@ver' -> 'ns_name' (processor package).
    Example: 'llm/litellm@1' -> 'llm_litellm'
    """
    ns, rest = ref.split("/", 1)
    name, _ver = rest.split("@", 1)
    return f"{ns}_{name}"


def _ensure_json_file(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _tar_directory(root: Path) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(mode="w:gz", fileobj=buf) as tf:
        for p in sorted(root.rglob("*")):
            arcname = p.relative_to(root.parent)  # include the top dir in archive
            tf.add(p, arcname=str(arcname))
    return buf.getvalue()


# -------------------------------
# Modal image & secrets wiring
# -------------------------------

IMAGE_REF = os.environ.get("IMAGE_REF")  # e.g. ghcr.io/owner/repo/llm-litellm@sha256:...
if not IMAGE_REF:
    raise RuntimeError("IMAGE_REF is required (OCI digest for the processor container)")

PROCESSOR_REF = os.environ.get("PROCESSOR_REF")  # e.g. llm/litellm@1
if not PROCESSOR_REF:
    raise RuntimeError("PROCESSOR_REF is required (e.g. 'llm/litellm@1')")

TOOL_SECRETS = _parse_tool_secrets(os.environ.get("TOOL_SECRETS"))

# Build Modal image from the pinned container
image = modal.Image.from_registry(IMAGE_REF)

app = modal.App("theory-runtime")


def _modal_secret_objects(names: Iterable[str]) -> List[modal.Secret]:
    secrets: List[modal.Secret] = []
    for n in names:
        if not n:
            continue
        # Will raise at deploy if a name is unknown in the target environment.
        secrets.append(modal.Secret.from_name(n))
    return secrets


# -------------------------------
# Core worker implementation
# -------------------------------


def _invoke_processor(payload: dict) -> bytes:
    """
    Execute the processor inside the pinned container:
      python -m apps.core.processors.<pkg>.main --inputs <file> --write-prefix <dir> --execution-id <id>
    Return: gzipped tarball of <write-prefix> contents (adapter will unpack & read outputs.json).
    """
    pkg = _pkg_from_ref(PROCESSOR_REF)

    # Make a temp working dir for inputs/outputs, but the processor will write to write_prefix we pass in.
    with tempfile.TemporaryDirectory() as tmpdir:
        work = Path(tmpdir)
        inputs_path = work / "inputs.json"

        # Ensure we have a mode: default to "mock" if not provided (safer for deploy smoke and CI).
        payload = dict(payload or {})
        payload.setdefault("schema", "v1")
        payload.setdefault("mode", "mock")

        # Ensure a stable execution id if provided, else create one
        execution_id = payload.get("execution_id") or str(uuid.uuid4())
        payload["execution_id"] = execution_id

        # Default write prefix (container-local). Adapters/Modal will pack and return this directory.
        write_prefix = payload.get("write_prefix") or f"/tmp/exec/{execution_id}/"
        payload["write_prefix"] = write_prefix

        _ensure_json_file(inputs_path, payload)

        cmd = [
            "python",
            "-m",
            f"apps.core.processors.{pkg}.main",
            "--inputs",
            str(inputs_path),
            "--write-prefix",
            write_prefix,
            "--execution-id",
            execution_id,
        ]

        _log(
            "modal.exec.start",
            processor_ref=PROCESSOR_REF,
            image_ref=IMAGE_REF,
            mode=payload.get("mode"),
            execution_id=execution_id,
            write_prefix=write_prefix,
        )

        # Run inside the same container env as this Modal function
        # NOTE: Secrets are attached at the function level (see decorators below), not here.
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        if proc.returncode != 0:
            _log(
                "modal.exec.fail",
                code="ERR_ADAPTER_INVOCATION",
                execution_id=execution_id,
                rc=proc.returncode,
                stderr=proc.stderr[-4000:],  # cap
            )
            # Return a small error envelope tar with the stderr for diagnostics
            # (Adapters can handle error envelopes too, but returning tar keeps a single wire shape.)
            err_dir = work / "error" / execution_id
            err_dir.mkdir(parents=True, exist_ok=True)
            (err_dir / "stderr.txt").write_text(proc.stderr, encoding="utf-8")
            (err_dir / "status.json").write_text(
                json.dumps(
                    {
                        "status": "error",
                        "execution_id": execution_id,
                        "error": {
                            "code": "ERR_ADAPTER_INVOCATION",
                            "message": f"Subprocess failed rc={proc.returncode}",
                        },
                        "meta": {"env_fingerprint": "adapter=modal"},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            return _tar_directory(err_dir)

        # Success: tar the entire write_prefix (which contains outputs.json and files)
        out_root = Path(write_prefix)
        if not out_root.exists():
            # Some processors might write relative to cwd; try fallback to /work/out
            candidate = Path("/work/out")
            if candidate.exists():
                out_root = candidate

        if not out_root.exists():
            _log(
                "modal.exec.warn",
                warning="write_prefix_not_found",
                attempted=str(write_prefix),
            )

        archive = _tar_directory(out_root if out_root.exists() else Path(tmpdir))
        _log(
            "modal.exec.complete",
            execution_id=execution_id,
            bytes=len(archive),
        )
        return archive


# -------------------------------
# Modal functions
# -------------------------------


@app.function(
    name="run",
    image=image,
    # Attach secrets dynamically based on TOOL_SECRETS env; nothing is hard-coded.
    secrets=_modal_secret_objects(TOOL_SECRETS),
    timeout=60 * 10,  # 10 minutes, adjust as needed
)
def run(payload: dict) -> bytes:
    """
    Normal execution:
      - Uses secrets defined in TOOL_SECRETS (if any).
      - Respects payload["mode"] ("real" or "mock"); default is "mock" if omitted.
      - Returns a gzipped tarball of the write_prefix directory.
    """
    if not isinstance(payload, dict):
        payload = {}
    return _invoke_processor(payload)


@app.function(
    name="smoke",
    image=image,
    # No secrets attached for smoke; ensures zero-egress mock-only validation.
    secrets=[],
    timeout=60 * 5,  # quicker timeout for smoke
)
def smoke(payload: dict) -> bytes:
    """
    Smoke validation:
      - Forces payload["mode"] = "mock"
      - Attaches no secrets (safe-by-default)
      - Returns tarball of outputs (like 'run')
    """
    if not isinstance(payload, dict):
        payload = {}
    payload = dict(payload)
    payload["mode"] = "mock"
    return _invoke_processor(payload)
