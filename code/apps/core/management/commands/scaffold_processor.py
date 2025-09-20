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

REF_RE = re.compile(r"^(?P<ns>[a-z0-9][a-z0-9_-]*)/(?P<name>[a-z0-9][a-z0-9_-]*)@(?P<ver>[0-9]+)$")


@dataclass(frozen=True)
class ProcessorRef:
    ns: str
    name: str
    ver: str

    @property
    def pkg(self) -> str:
        """Processor package folder name (Python-safe)."""
        return f"{self.ns}_{self.name}"

    @property
    def image_repo(self) -> str:
        """Container image repo naming (dash-separated for GHCR)."""
        return f"{self.ns.replace('_', '-')}-{self.name.replace('_', '-')}"

    @property
    def display(self) -> str:
        return f"{self.ns}/{self.name}@{self.ver}"


def parse_ref(ref: str) -> ProcessorRef:
    m = REF_RE.match(ref.strip())
    if not m:
        raise CommandError(f"Invalid --ref '{ref}'. Expected format 'ns/name@ver' (e.g., 'llm/litellm@1').")
    return ProcessorRef(ns=m.group("ns"), name=m.group("name"), ver=m.group("ver"))


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_file(path: Path, content: str, *, force: bool) -> None:
    if path.exists() and not force:
        raise CommandError(f"Refusing to overwrite existing file without --force: {path}")
    path.write_text(content, encoding="utf-8")


def repo_and_owner() -> Tuple[str, str]:
    """
    Derive 'owner/repo' for GHCR repo-scoped images.
    Priority:
      1) GITHUB_REPOSITORY env (CI)
      2) settings.GITHUB_REPOSITORY (if you set it)
      3) Fallback: directory name as 'owner/repo' => '<user>/<basename>'
    """
    env_val = os.getenv("GITHUB_REPOSITORY") or getattr(settings, "GITHUB_REPOSITORY", None)
    if env_val:
        return tuple(env_val.split("/", 1))  # type: ignore[return-value]
    # Fallback: repo name from BASE_DIR
    base = Path(settings.BASE_DIR).resolve()
    owner = os.getenv("GITHUB_ACTOR", "owner")
    return owner, base.name


def normalize_secret_names(secrets_csv: str | None) -> List[str]:
    if not secrets_csv:
        return []
    raw = [s.strip() for s in secrets_csv.split(",")]
    return [s for s in raw if s]


# -------------------------
# Templates
# -------------------------

T_MAIN = """\
\"\"\"Thin processor entrypoint for {ref.display}.

Responsibilities:
- Parse args (delegated to libs.runtime_common.processor)
- Load inputs (delegated)
- Resolve mode (libs.runtime_common.mode)
- Call provider runner (make_runner(config)(inputs))
- Write outputs + dual receipts (libs.runtime_common.*)
- No Django imports beyond this file; safe for container execution.
\"\"\"
from __future__ import annotations
import os, sys, time, json
from pathlib import Path
from typing import Any, Dict

from libs.runtime_common.processor import parse_args, load_inputs, ensure_write_prefix
from libs.runtime_common.mode import resolve_mode
from libs.runtime_common.hashing import inputs_hash
from libs.runtime_common.outputs import write_outputs, write_outputs_index
from libs.runtime_common.receipts import write_dual_receipts

from apps.core.processors.{ref.pkg}.provider import make_runner

PROCESSOR_REF = "{ref.display}"

def main() -> int:
    args = parse_args()  # --inputs, --write-prefix, --execution-id, --mode (optional)
    write_prefix = ensure_write_prefix(args.write_prefix)
    inputs: Dict[str, Any] = load_inputs(args.inputs)

    # Harmonize mode into inputs (CLI --mode wins if present)
    if args.mode:
        inputs = dict(inputs)
        inputs["mode"] = args.mode

    # Resolve mode early (for receipts/meta if desired)
    mode = resolve_mode(inputs).value

    # Prepare runner and execute
    runner = make_runner(config={})
    t0 = time.time()
    result: Dict[str, Any] = runner(inputs)
    duration_ms = int((time.time() - t0) * 1000)

    # Normalize outputs: expect list of {"relpath": "...", "bytes": b"...", "mime": "..."} in result.get("outputs", [])
    outputs = result.get("outputs", [])
    abs_paths = write_outputs(write_prefix, outputs)
    idx_path = write_outputs_index(
        execution_id=args.execution_id,
        write_prefix=write_prefix,
        paths=abs_paths,
    )

    # Build receipt
    ih = inputs_hash(inputs)
    receipt = {{
        "execution_id": args.execution_id,
        "processor_ref": PROCESSOR_REF,
        "image_digest": os.getenv("IMAGE_REF", "unknown"),
        "env_fingerprint": os.getenv("ENV_FINGERPRINT", ""),
        "inputs_hash": ih["value"],
        "hash_schema": ih["hash_schema"],
        "outputs_index": str(idx_path),
        "processor_info": result.get("processor_info", PROCESSOR_REF),
        "usage": result.get("usage", {{}}),
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "duration_ms": duration_ms,
        "mode": mode,
    }}
    write_dual_receipts(args.execution_id, write_prefix, receipt)

    # Print success envelope to stdout for adapters
    payload = {{
        "status": "success",
        "execution_id": args.execution_id,
        "outputs": [p.as_posix() for p in abs_paths],
        "index_path": str(idx_path),
        "meta": {{"env_fingerprint": os.getenv("ENV_FINGERPRINT", "")}},
    }}
    sys.stdout.write(json.dumps(payload))
    sys.stdout.flush()
    return 0

if __name__ == "__main__":
    sys.exit(main())
"""

T_PROVIDER = """\
\"\"\"Provider facade for {ref.display}.

Expose a single uniform callable runner:

    runner = make_runner(config={{{}}})
    result = runner(inputs: dict) -> dict

Contract for `result`:
- processor_info: str (e.g., "{ref.display}")
- usage: dict (timings, tokens, costs, optional)
- outputs: list of artifacts to write (optional)
- result: provider-specific payload (optional)

In MOCK mode, no secrets should be required and results are deterministic.
\"\"\"
from __future__ import annotations
import os
from typing import Any, Dict
from libs.runtime_common.mode import resolve_mode, is_mock

def make_runner(config: Dict[str, Any]):
    def run(inputs: Dict[str, Any]) -> Dict[str, Any]:
        m = resolve_mode(inputs)
        if is_mock(m):
            text = "MOCK: hello world"
            out_bytes = text.encode("utf-8")
            return {{
                "processor_info": "{ref.display}",
                "usage": {{}},
                "outputs": [
                    {{"relpath": "outputs/response.json", "bytes": out_bytes, "mime": "application/json"}}
                ],
                "result": {{"text": text}},
            }}

        # REAL path: example shows a trivial echo; replace with actual provider logic.
        # Require secrets explicitly if needed:
        # api_key = os.getenv("OPENAI_API_KEY")
        # if not api_key:
        #     raise RuntimeError("ERR_MISSING_SECRET: OPENAI_API_KEY")

        text = "REAL: hello world"
        out_bytes = text.encode("utf-8")
        return {{
            "processor_info": "{ref.display}",
            "usage": {{}},
            "outputs": [
                {{"relpath": "outputs/response.json", "bytes": out_bytes, "mime": "application/json"}}
            ],
            "result": {{"text": text}},
        }}
    return run
"""

T_DOCKERFILE = """\
# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \\
    PYTHONUNBUFFERED=1

WORKDIR /work

# System deps (add as needed)
RUN apt-get update -y && apt-get install -y --no-install-recommends \\
    ca-certificates curl && \\
    rm -rf /var/lib/apt/lists/*

# App deps
# IMPORTANT: Build context assumed at repo root.
COPY code/apps/core/processors/{pkg}/requirements.txt /work/requirements.txt
RUN pip install --no-cache-dir -r /work/requirements.txt

# App code
COPY code /work

# Entrypoint executes the processor main in the container
ENTRYPOINT ["python", "-m", "apps.core.processors.{pkg}.main"]
"""

T_REQUIREMENTS = """\
# Add processor-specific Python deps here.
# Keep minimal; prefer using libs/runtime_common from repo code mount.
"""


def _yaml_block_list(key: str, items: Iterable[str], indent: int = 2) -> str:
    pad = " " * indent
    if not items:
        return ""
    lines = [f"{pad}{key}:"]
    for s in items:
        lines.append(f"{pad}- {s}")
    return "\n".join(lines) + "\n"


T_REGISTRY = """\
# Registry spec for {ref.display}
image:
  oci: ghcr.io/{owner_repo}/{image_repo}@sha256:pending
runtime:
  cpu: 1
  memory: 2gb
  gpu: none
{secrets_block}"""


# -------------------------
# Management Command
# -------------------------


class Command(BaseCommand):
    help = "Scaffold a new processor (code files + registry spec) using the thin, shared-runtime pattern."

    def add_arguments(self, parser):
        parser.add_argument(
            "--ref",
            required=True,
            help="Processor reference in form 'ns/name@ver' (e.g., 'llm/litellm@1').",
        )
        parser.add_argument(
            "--secrets",
            default="",
            help="Comma-separated secret names required by this processor (e.g., 'OPENAI_API_KEY,FOO').",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Allow overwriting existing files (use with care).",
        )

    def handle(self, *args, **opts):
        ref = parse_ref(opts["ref"])
        secrets = normalize_secret_names(opts.get("secrets"))
        force: bool = bool(opts.get("force"))

        # Resolve repo structure
        repo_root = Path(settings.BASE_DIR).resolve()  # repo root
        code_dir = repo_root / "code"
        if not code_dir.exists():
            raise CommandError(f"Expected 'code/' at repo root but not found: {code_dir}")

        processors_dir = code_dir / "apps" / "core" / "processors" / ref.pkg
        registry_dir = code_dir / "apps" / "core" / "registry" / "processors"

        ensure_dir(processors_dir)
        ensure_dir(registry_dir)

        # Compute files
        main_py = processors_dir / "main.py"
        provider_py = processors_dir / "provider.py"
        reqs_txt = processors_dir / "requirements.txt"
        dockerfile = processors_dir / "Dockerfile"
        registry_yaml = registry_dir / f"{ref.pkg}.yaml"

        # Owner/repo for GHCR
        owner, repo = repo_and_owner()
        owner_repo = f"{owner}/{repo}"

        # Render content
        main_src = T_MAIN.format(ref=ref)
        provider_src = T_PROVIDER.format(ref=ref)
        docker_src = T_DOCKERFILE.format(pkg=ref.pkg)
        reqs_src = T_REQUIREMENTS
        secrets_blk = _yaml_block_list("secrets", secrets, indent=0)
        registry_src = T_REGISTRY.format(
            ref=ref,
            owner_repo=owner_repo,
            image_repo=ref.image_repo,
            secrets_block=secrets_blk,
        )

        # Write files
        write_file(main_py, main_src, force=force)
        write_file(provider_py, provider_src, force=force)
        write_file(reqs_txt, reqs_src, force=force)
        write_file(dockerfile, docker_src, force=force)
        write_file(registry_yaml, registry_src, force=force)

        # Summary
        created = [main_py, provider_py, reqs_txt, dockerfile, registry_yaml]
        rels = [p.relative_to(repo_root).as_posix() for p in created]
        self.stdout.write(self.style.SUCCESS("✓ Processor scaffold created"))
        for r in rels:
            self.stdout.write(f"  - {r}")

        # Next steps (explicit, concise)
        self.stdout.write("\nNext steps:")
        self.stdout.write("  1) Commit & push these files.")
        self.stdout.write(
            "  2) Run Build & Pin workflow to build & publish GHCR image (pinned digest will update registry)."
        )
        if secrets:
            pretty = ", ".join(secrets)
            self.stdout.write(f"  3) Ensure Modal has secrets: {pretty} in your target environment(s).")
        self.stdout.write("  4) Run acceptance tests and modal deploy smoke (mock).")
