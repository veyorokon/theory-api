# code/apps/core/management/commands/tools/scaffold_tool.py
from __future__ import annotations
import re
import textwrap
import pathlib
from django.core.management.base import BaseCommand, CommandError

REF_RE = re.compile(r"^(?P<ns>[a-z0-9_\-]+)/(?P<name>[a-z0-9_\-]+)@(?P<ver>[0-9]+)$")


class Command(BaseCommand):
    help = "Scaffold a minimal container-first WS tool with protocol layer from runtime_common."

    def add_arguments(self, parser):
        parser.add_argument("--ref", required=True, help="ns/name@ver (e.g., llm/litellm@1)")
        parser.add_argument("--secrets", default="", help="comma-separated secret names (e.g., OPENAI_API_KEY,FOO)")
        parser.add_argument("--cpu", default="1", help='CPU (string, e.g. "1")')
        parser.add_argument("--memory", type=int, default=2, help="Memory (GiB)")
        parser.add_argument("--timeout", type=int, default=600, help="Timeout seconds")
        parser.add_argument("--gpu", default="", help="GPU type (e.g., a10g) or empty")
        parser.add_argument("--force", action="store_true", help="Overwrite existing files")

    def handle(self, *args, **opts):
        from django.conf import settings

        ref = opts["ref"]
        m = REF_RE.match(ref)
        if not m:
            raise CommandError("ref must match ns/name@ver (e.g., llm/litellm@1)")

        ns, name, ver = m.group("ns"), m.group("name"), m.group("ver")

        # Use TOOLS_ROOTS (first root only)
        roots = settings.TOOLS_ROOTS
        if not roots:
            raise CommandError("TOOLS_ROOTS not configured in settings")

        root = roots[0]
        tool_dir = root / ns / name / ver
        protocol_dir = tool_dir / "protocol"
        force = opts["force"]
        secrets = [s.strip() for s in (opts["secrets"] or "").split(",") if s.strip()]
        cpu, memory_gb, timeout_s, gpu = opts["cpu"], int(opts["memory"]), int(opts["timeout"]), (opts["gpu"] or None)

        if tool_dir.exists() and not force:
            raise CommandError(f"{tool_dir} already exists (use --force to overwrite).")

        tool_dir.mkdir(parents=True, exist_ok=True)
        protocol_dir.mkdir(parents=True, exist_ok=True)

        # Write minimal scaffold
        self._write(tool_dir / "Dockerfile", self._render_dockerfile(ns, name, ver))
        self._write(
            tool_dir / "registry.yaml",
            self._render_registry_yaml(ns, name, ver, cpu, memory_gb, timeout_s, gpu, secrets),
        )
        self._write(protocol_dir / "__init__.py", "")

        self.stdout.write(self.style.SUCCESS(f"Scaffolded minimal tool at {tool_dir}"))
        self.stdout.write("  Protocol layer: code/libs/runtime_common/protocol/")
        self.stdout.write(f"  Override handler: {protocol_dir}/handler.py")

    def _write(self, path: pathlib.Path, content: str):
        path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")

    # ------------------ Templates ------------------

    def _render_dockerfile(self, ns: str, name: str, ver: str) -> str:
        return f"""
        FROM python:3.11-slim

        ENV PYTHONDONTWRITEBYTECODE=1 \\
            PYTHONUNBUFFERED=1 \\
            TZ=UTC \\
            LC_ALL=C.UTF-8

        RUN apt-get update && apt-get install -y --no-install-recommends \\
            curl ca-certificates \\
            && rm -rf /var/lib/apt/lists/*

        WORKDIR /tool

        # Copy protocol layer from runtime_common
        COPY code/libs/runtime_common /tool/libs/runtime_common

        # Copy tool-specific overrides (if any)
        COPY tools/{ns}/{name}/{ver}/protocol /tool/protocol

        RUN pip install --no-cache-dir \\
            "fastapi>=0.114" \\
            "uvicorn[standard]>=0.30" \\
            "pydantic>=2.8" \\
            "requests>=2.32" \\
            "httpx>=0.27"

        # Writable HOME for pip/model caching
        RUN mkdir -p /home/app && chmod -R 0777 /home/app
        ENV HOME=/home/app

        # Writable /artifacts for local output mode
        RUN mkdir -p /artifacts && chmod -R 0777 /artifacts

        EXPOSE 8000
        CMD ["uvicorn", "protocol.ws:app", "--host", "0.0.0.0", "--port", "8000"]

        HEALTHCHECK --interval=10s --timeout=3s --retries=5 \\
          CMD curl -sf http://localhost:8000/healthz || exit 1
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
    ) -> str:
        inputs_schema = {
            "$schema": "https://json-schema.org/draft-07/schema#",
            "title": f"{ns}/{name} inputs v1",
            "type": "object",
            "additionalProperties": True,
        }
        outputs = [{"path": "result.json", "mime": "application/json", "description": "Execution result"}]

        yaml_obj = {
            "ref": f"{ns}/{name}@{ver}",
            "enabled": False,
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
