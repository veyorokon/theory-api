"""
Self-contained Modal deploy module (no Django/repo imports, no codegen).

Deploy:
  modal deploy --env $MODAL_ENVIRONMENT -m modal_app

Runtime (adapter):
  Function.from_name(app=APP_NAME, name="run", environment_name=$MODAL_ENVIRONMENT)

CI smoke:
  Function.from_name(..., name="smoke")  # deterministic, zero-cost
"""

from __future__ import annotations

import io
import os
import json
import tarfile
import subprocess
from typing import List

import modal
from apps.core.adapters.modal.naming import modal_app_name_from_ref, modal_fn_name


# ---------- Naming ----------


def _app_name_from_env() -> str:
    """Build app name from PROCESSOR_REF and MODAL_ENVIRONMENT using shared helper."""
    ref = os.environ.get("PROCESSOR_REF", "")
    env = os.environ.get("MODAL_ENVIRONMENT") or os.environ.get("MODAL_ENV") or "dev"
    if ref:
        return modal_app_name_from_ref(ref, env)
    return os.getenv("MODAL_APP_NAME", "theory-rt")


APP_NAME = _app_name_from_env()
app = modal.App(APP_NAME)


# ---------- Parameters (env-only) ----------

# Required
PROCESSOR_REF = os.environ["PROCESSOR_REF"]  # e.g. "llm/litellm@1"
IMAGE_REF = os.environ["IMAGE_REF"]  # e.g. "ghcr.io/...@sha256:deadbeef..."

# Optional
TIMEOUT_S = int(os.getenv("TIMEOUT_S", "60"))
CPU = int(os.getenv("CPU", "1"))
MEMORY_MIB = int(os.getenv("MEMORY_MIB", "2048"))  # MiB
GPU: str | None = os.getenv("GPU") or None  # e.g., "A10G" or unset

# Registry secret (must contain REGISTRY_USERNAME + REGISTRY_PASSWORD)
REGISTRY_SECRET_NAME = os.getenv("REGISTRY_SECRET_NAME", "REGISTRY_AUTH")

# Comma-separated workload secrets; names must equal env var names
TOOL_SECRETS: List[str] = [s for s in (os.getenv("TOOL_SECRETS", "")).split(",") if s.strip()]

# Image + secrets
image = modal.Image.from_registry(
    IMAGE_REF,
    secret=modal.Secret.from_name(REGISTRY_SECRET_NAME),
)

secrets = [modal.Secret.from_name(REGISTRY_SECRET_NAME)]
for s in TOOL_SECRETS:
    secrets.append(modal.Secret.from_name(s))


# ---------- Shared execution ----------


def _exec(payload: dict, *, extra_env: dict | None = None) -> bytes:
    """
    Write inputs -> call /app/main.py -> tar /work/out into gzipped bytes.
    """
    # 1) Inputs
    os.makedirs("/work", exist_ok=True)
    inputs_path = "/work/inputs.json"
    with open(inputs_path, "w", encoding="utf-8") as f:
        json.dump(payload["inputs_json"], f, ensure_ascii=False, separators=(",", ":"))

    write_prefix = payload["write_prefix"]
    argv = ["python", "/app/main.py", "--inputs", inputs_path, "--write-prefix", write_prefix]

    # 2) Run
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)

    try:
        proc = subprocess.run(
            argv,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
    except subprocess.CalledProcessError as e:
        tail = (e.stderr or "").splitlines()[-40:]
        raise RuntimeError(f"processor failed (exit={e.returncode}):\n" + "\n".join(tail))

    # 3) Tar outputs
    buf = io.BytesIO()
    out_dir = "/work/out"
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        if os.path.isdir(out_dir):
            for root, _, files in os.walk(out_dir):
                for fn in files:
                    full = os.path.join(root, fn)
                    arc = os.path.relpath(full, out_dir)
                    tf.add(full, arcname=arc)
    buf.seek(0)
    return buf.read()


# ---------- Functions ----------


# Real function: used in production/runtime
@app.function(
    name="run",
    image=image,
    timeout=TIMEOUT_S,
    cpu=CPU,
    memory=MEMORY_MIB,
    gpu=GPU,
    secrets=secrets,
    retries=0,  # fail-fast; policy is upstream
    serialized=True,  # stable name requires serialization
)
def run(payload: dict) -> bytes:
    return _exec(payload)


# Deterministic, zero-cost smoke function: used only by CI post-deploy
@app.function(
    name="smoke",
    image=image,
    timeout=TIMEOUT_S,
    cpu=CPU,
    memory=MEMORY_MIB,
    gpu=GPU,
    secrets=secrets,
    retries=0,
    serialized=True,
)
def smoke(payload: dict) -> bytes:
    import os

    # Clear API keys to force mock mode
    for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY"):
        os.environ.pop(k, None)
    # Ensure mode is set to smoke
    if isinstance(payload, dict):
        payload["mode"] = "smoke"
    return run(payload)
