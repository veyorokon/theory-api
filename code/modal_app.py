"""
Self-contained Modal deploy module (no repo imports, no dynamic codegen).
Parametrized entirely by environment variables so CI and local dev can deploy
the same module without generating files or running a separate deployer.

Usage (deploy):
  modal deploy --env $MODAL_ENVIRONMENT -m modal_app

Invocation (adapter):
  modal.Function.from_name(app=APP_NAME, name=FN_NAME, environment_name=ENV).remote(payload)
"""

import io
import os
import json
import tarfile
import subprocess
from typing import List

import modal

# Stable app name; environment is selected at deploy/invoke time
APP_NAME = os.getenv("MODAL_APP_NAME", "theory-rt")
app = modal.App(APP_NAME)

# Deployment-time parameters (all via env)
# Required
PROCESSOR_REF = os.environ["PROCESSOR_REF"]           # e.g. "llm/litellm@1"
IMAGE_REF     = os.environ["IMAGE_REF"]               # e.g. "ghcr.io/..@sha256:..."
# Optional (with sane defaults)
TIMEOUT_S  = int(os.getenv("TIMEOUT_S", "60"))
CPU        = int(os.getenv("CPU", "1"))
MEMORY_MIB = int(os.getenv("MEMORY_MIB", "2048"))  # Modal uses MiB
GPU        = os.getenv("GPU") or None                # e.g., "A10G" or unset -> None

# Comma-separated list of tool secret names (must match env var names)
TOOL_SECRETS: List[str] = [s for s in (os.getenv("TOOL_SECRETS", "")).split(",") if s.strip()]

# Registry auth secret (special case: contains REGISTRY_USERNAME/REGISTRY_PASSWORD)
REGISTRY_SECRET_NAME = "REGISTRY_AUTH"

# Modal image & secrets list
image = modal.Image.from_registry(IMAGE_REF, secret=modal.Secret.from_name(REGISTRY_SECRET_NAME))
secrets = [modal.Secret.from_name(REGISTRY_SECRET_NAME)]
for s in TOOL_SECRETS:
    secrets.append(modal.Secret.from_name(s))


def _fn_name(ref: str) -> str:
    """Deterministic function name: exec__{slug}__v{ver} from 'ns/name@ver'."""
    name, ver = ref.split("@", 1)
    return f"exec__{name.replace('/', '_')}__v{ver}"


FN_NAME = _fn_name(PROCESSOR_REF)


@app.function(
    name=FN_NAME,                # deterministic; adapter can resolve by name
    image=image,
    timeout=TIMEOUT_S,
    cpu=CPU,
    memory=MEMORY_MIB,
    gpu=GPU,
    secrets=secrets,
    retries=0,                   # fail-fast; caller handles policy/retry
    serialized=True,             # required when using custom name
)
def _exec(payload: dict) -> bytes:
    """
    Execute processor inside container image and return gzipped tar of /work/out.

    Payload contract:
      {
        "inputs_json": {...},           # dict
        "write_prefix": "/artifacts/..."  # string (must end with '/')
      }
    """
    # 1) Write inputs to /work
    os.makedirs("/work", exist_ok=True)
    inputs_path = "/work/inputs.json"
    with open(inputs_path, "w", encoding="utf-8") as f:
        json.dump(payload["inputs_json"], f, ensure_ascii=False, separators=(",", ":"))

    # 2) Run processor entrypoint
    write_prefix = payload["write_prefix"]
    argv = ["python", "/app/main.py", "--inputs", inputs_path, "--write-prefix", write_prefix]

    try:
        subprocess.run(
            argv,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        tail = (e.stderr or "").splitlines()[-40:]
        raise RuntimeError("processor failed (exit=%s):\n%s" % (e.returncode, "\n".join(tail)))

    # 3) Tar /work/out into bytes
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
