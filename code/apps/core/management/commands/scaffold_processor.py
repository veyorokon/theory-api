# apps/core/management/commands/scaffold_processor.py
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

from django.core.management.base import BaseCommand, CommandError


HELP = """Scaffold a new processor using the thin, provider-agnostic pattern.

Creates:
  apps/core/processors/<ns>_<name>/
    - main.py            # thin entrypoint (parse->normalize->runner->outputs->receipts)
    - provider.py        # make_runner(ProviderConfig)->callable(inputs)->ProcessorResult
    - requirements.txt   # processor-only deps (no Django)
    - Dockerfile         # containerized processor (ENTRYPOINT to main)

Optionally (with --with-registry):
  apps/core/registry/processors/<ns>_<name>.yaml  # pinned image placeholder + runtime + secrets

Usage:
  python manage.py scaffold_processor --ref replicate/generic@1 --with-registry --secrets REPLICATE_API_TOKEN
"""


# -------------------------- templates (edit as needed) --------------------------

TEMPLATE_MAIN = '''"""Processor entrypoint (thin pattern, provider-agnostic).

Contract:
- No Django imports here.
- Uses runtime_common helpers for args, inputs, hashing, outputs, receipts.
- Provider surface: make_runner(ProviderConfig) -> callable(inputs: dict) -> ProcessorResult
"""
from __future__ import annotations

import os
import sys
import time
from typing import Any, Dict

from libs.runtime_common.processor import parse_args, load_inputs, ensure_write_prefix
from libs.runtime_common.hashing import inputs_hash
from libs.runtime_common.fingerprint import compose_env_fingerprint
from libs.runtime_common.outputs import write_outputs, write_outputs_index
from libs.runtime_common.receipts import write_dual_receipts
from libs.runtime_common.mode import resolve_mode

from .provider import make_runner


def _env_fingerprint() -> str:
    # Keep stable, cheap, and sorted
    return compose_env_fingerprint(
        image=os.getenv("IMAGE_REF", "unknown"),
        cpu=os.getenv("CPU", "1"),
        memory=os.getenv("MEMORY", "2Gi"),
        py=os.getenv("PYTHON_VERSION", ""),
        gpu=os.getenv("GPU", "none"),
    )


def main() -> int:
    args = parse_args()
    write_prefix = ensure_write_prefix(args.write_prefix)
    inputs = load_inputs(args.inputs)

    ih = inputs_hash(inputs)
    mode = resolve_mode(inputs)
    config = {}  # Provider-specific config as needed

    runner = make_runner(config)

    t0 = time.time()
    result = runner(inputs)  # callable(inputs) -> ProcessorResult
    duration_ms = int((time.time() - t0) * 1000)

    abs_paths = write_outputs(write_prefix, result.outputs, enforce_outputs_prefix=True)
    index_path = write_outputs_index(
        execution_id=args.execution_id,
        write_prefix=write_prefix,
        paths=abs_paths,
    )

    receipt = {
        "execution_id": args.execution_id,
        "processor_ref": os.getenv("PROCESSOR_REF", "{REF}"),
        "image_digest": os.getenv("IMAGE_REF", "unknown"),
        "env_fingerprint": _env_fingerprint(),
        "inputs_hash": ih["value"],
        "hash_schema": ih["hash_schema"],
        "outputs_index": str(index_path),
        "processor_info": result.processor_info,
        "usage": result.usage,
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "duration_ms": duration_ms,
        "extra": result.extra,
    }
    write_dual_receipts(args.execution_id, write_prefix, receipt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''

TEMPLATE_PROVIDER = '''"""Provider stub for {REF}.

This file **stays inside the processor container**.
- It must not import Django.
- If you need an SDK (e.g., replicate, litellm), add it to requirements.txt and import here.
- The only public contract is: make_runner(ProviderConfig) -> callable(inputs: dict) -> ProcessorResult
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Mapping, Optional

# Import shared types
from libs.runtime_common.outputs import OutputItem
from libs.runtime_common.types import ProcessorResult
from libs.runtime_common.mode import resolve_mode, is_mock


def _make_mock_runner(config: Dict[str, Any]) -> Callable[[Dict[str, Any]], ProcessorResult]:
    def _runner(inputs: Dict[str, Any]) -> ProcessorResult:
        # Minimal, deterministic mock
        model = inputs.get("model", "mock-model")
        payload = f"mock response from {model}".encode("utf-8")
        return ProcessorResult(
            outputs=[OutputItem(relpath="outputs/result.txt", bytes_=payload, mime="text/plain")],
            processor_info={"provider": "mock", "model": model},
            usage={},
            extra={"mode": "mock"},
        )
    return _runner


def _make_real_runner(config: Dict[str, Any]) -> Callable[[Dict[str, Any]], ProcessorResult]:
    # TODO: Import and use your real SDK(s) here.
    # Example (pseudocode):
    #   import some_sdk
    #   client = some_sdk.Client(api_key=cfg.extra.get("API_KEY"))
    #   def _runner(inputs: Dict[str, Any]) -> ProcessorResult:
    #       model = inputs.get("model") or cfg.model
    #       params = inputs.get("params", {})
    #       data = client.run(model=model, **params)
    #       # Normalize to OutputItem(s)
    #       content = (str(data) + "\\n").encode("utf-8")
    #       return ProcessorResult(
    #           outputs=[OutputItem(relpath="outputs/result.txt", bytes_=content, mime="text/plain")],
    #           processor_info={"provider": "real", "model": model or "no-model"},
    #           usage={},
    #           extra={"mode": "real"},
    #       )
    #   return _runner
    def _runner(_inputs: Dict[str, Any]) -> ProcessorResult:
        raise RuntimeError("Real runner not implemented yet. Fill in provider logic.")
    return _runner


def make_runner(config: Dict[str, Any]) -> Callable[[Dict[str, Any]], ProcessorResult]:
    \"\"\"Returns a callable(inputs) -> ProcessorResult.
    - inputs expects: {\"schema\":\"v1\",\"model\":\"...\",\"params\":{...},\"mode\":\"real|mock|smoke\"}
    \"\"\"
    def _runner(inputs: Dict[str, Any]) -> ProcessorResult:
        mode = resolve_mode(inputs)
        if is_mock(mode):
            return _make_mock_runner(config)(inputs)
        return _make_real_runner(config)(inputs)
    return _runner
'''

TEMPLATE_REQUIREMENTS = """blake3
# Add any provider SDKs your processor needs below, e.g.:
# replicate
# litellm
"""

TEMPLATE_DOCKERFILE = """FROM python:3.11-slim
WORKDIR /work
# Prevents python from writing .pyc files & buffers stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY requirements.txt /work/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /work
ENTRYPOINT ["python", "-m", "apps.core.processors.{PKG}.main"]
"""

TEMPLATE_REGISTRY = """ref: {REF}
runtime:
  cpu: {CPU}
  memory: {MEMORY}
  gpu: {GPU}
image:
  # Pin with Build & Pin workflow; placeholder prevents accidental pulls
  oci: ghcr.io/{OWNER}/theory-api/{PKG}@sha256:pending
secrets:
  required:{SECRETS_BLOCK}
policy:
  network: egress
  max_file_mb: 100
  request_timeout_s: 120
"""


# -------------------------- utils --------------------------


@dataclass(frozen=True)
class Ref:
    ns: str
    name: str
    ver: str

    @property
    def pkg(self) -> str:
        return f"{self.ns}_{self.name}"

    @property
    def pretty(self) -> str:
        return f"{self.ns}/{self.name}@{self.ver}"


def parse_ref(ref: str) -> Ref:
    try:
        ns, rest = ref.split("/", 1)
        name, ver = rest.split("@", 1)
    except ValueError:
        raise CommandError(f"Invalid ref '{ref}'. Expected format: ns/name@ver")
    if not re.fullmatch(r"[a-z0-9\-]+", ns) or not re.fullmatch(r"[a-z0-9_\-]+", name):
        raise CommandError("Invalid characters in ns/name. Use lowercase, digits, '-', '_' for name.")
    if not re.fullmatch(r"[0-9]+", ver):
        raise CommandError("Version must be an integer (e.g., @1).")
    return Ref(ns=ns, name=name, ver=ver)


def parse_runtime(runtime: str) -> Tuple[str, str, str]:
    # "cpu=1,memory=2Gi,gpu=none"
    parts = dict(x.split("=", 1) for x in runtime.split(",") if "=" in x)
    return (
        parts.get("cpu", "1"),
        parts.get("memory", "2Gi"),
        parts.get("gpu", "none"),
    )


def format_secrets_block(secret_names: List[str]) -> str:
    if not secret_names:
        return " []"
    lines = "".join(f"\n    - {s}" for s in secret_names)
    return lines


# -------------------------- command --------------------------


class Command(BaseCommand):
    help = HELP

    def add_arguments(self, parser):
        parser.add_argument("--ref", required=True, help="Processor ref (ns/name@ver)")
        parser.add_argument("--with-registry", action="store_true", help="Also create registry YAML")
        parser.add_argument(
            "--runtime", default="cpu=1,memory=2Gi,gpu=none", help="Runtime CSV (cpu=1,memory=2Gi,gpu=none)"
        )
        parser.add_argument("--secrets", default="", help="Comma-separated secret names")
        parser.add_argument(
            "--owner", default="owner", help="Container registry namespace (for registry YAML placeholder)"
        )
        parser.add_argument("--force", action="store_true", help="Overwrite existing files if present")

    def handle(self, *args, **opts):
        ref = parse_ref(opts["ref"])
        cpu, mem, gpu = parse_runtime(opts["runtime"])
        secrets = [s.strip() for s in opts["secrets"].split(",") if s.strip()]
        owner = opts["owner"]
        force = opts["force"]

        proc_dir = Path(f"apps/core/processors/{ref.pkg}")
        proc_dir.mkdir(parents=True, exist_ok=True)

        # Files to write
        files = {
            proc_dir / "main.py": TEMPLATE_MAIN.replace("{REF}", ref.pretty),
            proc_dir / "provider.py": TEMPLATE_PROVIDER.replace("{REF}", ref.pretty),
            proc_dir / "requirements.txt": TEMPLATE_REQUIREMENTS,
            proc_dir / "Dockerfile": TEMPLATE_DOCKERFILE.replace("{PKG}", ref.pkg),
        }

        # Write processor files
        for path, content in files.items():
            if path.exists() and not force:
                raise CommandError(f"Refusing to overwrite existing file: {path} (use --force)")
            path.write_text(content, encoding="utf-8")

        # Optional registry YAML
        if opts["with_registry"]:
            reg_dir = Path("apps/core/registry/processors")
            reg_dir.mkdir(parents=True, exist_ok=True)
            reg_path = reg_dir / f"{ref.pkg}.yaml"
            if reg_path.exists() and not force:
                raise CommandError(f"Refusing to overwrite existing file: {reg_path} (use --force)")
            reg_yaml = TEMPLATE_REGISTRY.format(
                REF=ref.pretty,
                CPU=cpu,
                MEMORY=mem,
                GPU=gpu,
                OWNER=owner,
                PKG=ref.pkg,
                SECRETS_BLOCK=format_secrets_block(secrets),
            )
            reg_path.write_text(reg_yaml, encoding="utf-8")

        self.stdout.write(self.style.SUCCESS(f"✓ Scaffolded processor {ref.pretty} in {proc_dir}"))
        if opts["with_registry"]:
            self.stdout.write(
                self.style.SUCCESS(f"✓ Created registry spec at apps/core/registry/processors/{ref.pkg}.yaml")
            )
        self.stdout.write(
            "Next steps:\n"
            "  • Add real provider logic in provider.py (SDK import + real runner)\n"
            "  • Add any SDKs to requirements.txt\n"
            "  • Build & Pin to replace the placeholder digest in registry YAML\n"
        )
