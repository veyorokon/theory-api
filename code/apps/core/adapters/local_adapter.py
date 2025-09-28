from __future__ import annotations

import json
import os
import shlex
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict


import requests

from .base_http_adapter import (
    BaseHTTPAdapter,
    InvokeOptions,
    InvokeResult,
    _normalize_digest,
    _error_envelope,
)

# --- Logging -----------------------------------------------------------------
try:
    from libs.runtime_common.logging import info, warn, error, debug  # type: ignore
except Exception:  # pragma: no cover
    import logging

    _L = logging.getLogger("adapters.local")
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    def info(event: str, **fields):
        _L.info(json.dumps({"event": event, **fields}))

    def warn(event: str, **fields):
        _L.warning(json.dumps({"event": event, **fields}))

    def error(event: str, **fields):
        _L.error(json.dumps({"event": event, **fields}))

    def debug(event: str, **fields):
        _L.debug(json.dumps({"event": event, **fields}))


# --- Options -----------------------------------------------------------------
@dataclass(frozen=True)
class LocalInvokeOptions(InvokeOptions):
    image_ref: str | None = None  # resolved OCI or local build tag
    mount_artifacts: str | None = None  # e.g., "/artifacts"
    run_path: str = "/run"
    health_path: str = "/healthz"
    build: bool = False

    @classmethod
    def from_ref(cls, ref: str, **kwargs) -> LocalInvokeOptions:
        build = kwargs.pop("build", False)
        return cls(image_ref=_resolve_image_ref(ref, build=build), build=build, **kwargs)


# --- Registry helpers ---------------------------------------------------------
def _code_root() -> Path:
    # .../code/apps/core/adapters/local_adapter.py -> .../code
    return Path(__file__).resolve().parents[3]


def _registry_path(ref: str) -> Path:
    ns, rest = ref.split("/", 1)
    name, _ver = rest.split("@", 1)
    return _code_root() / "apps" / "core" / "processors" / f"{ns}_{name}" / "registry.yaml"


def _load_registry_for_ref(ref: str) -> Dict[str, Any]:
    reg_path = _registry_path(ref)
    if not reg_path.exists():
        raise FileNotFoundError(f"registry.yaml not found for ref '{ref}' at {reg_path}")
    try:
        import yaml  # type: ignore
    except ImportError as ie:  # pragma: no cover
        raise ImportError("PyYAML is required. Install with: pip install pyyaml") from ie
    with reg_path.open("r") as f:
        return yaml.safe_load(f) or {}


def _detect_arch() -> str:
    m = os.uname().machine
    return "amd64" if m == "x86_64" else ("arm64" if m in ("aarch64", "arm64") else m)


def _get_newest_build_tag(ref: str) -> str:
    """Find the newest timestamped build tag for theory-local/{ns}-{name}-{ver}:build-*"""
    ns, rest = ref.split("/", 1)
    name, ver = rest.split("@", 1)
    repo = f"theory-local/{ns}-{name}-{ver}"

    try:
        out = subprocess.check_output(
            ["docker", "image", "ls", "--format", "{{.Repository}}:{{.Tag}}|{{.CreatedAt}}", repo],
            stderr=subprocess.STDOUT,
            text=True,
        )
    except Exception:
        raise ValueError(f"No local build images found. Run: make build-processor REF={ref}")

    candidates = []
    for line in out.splitlines():
        try:
            tag_part, created = line.split("|", 1)
        except ValueError:
            continue
        if tag_part.startswith(f"{repo}:build-"):
            candidates.append((created, tag_part))

    if not candidates:
        raise ValueError(f"No local build images found. Run: make build-processor REF={ref}")

    # Sort by tag name timestamp (newest first), not Docker creation time
    # Tag format: theory-local/llm-litellm-1:build-YYYYMMDDHHMMSS
    # Docker's creation time can be misleading when layers are reused
    candidates_by_tag = [(tag.split(":build-")[1], tag) for created, tag in candidates]
    candidates_by_tag.sort(reverse=True, key=lambda x: x[0])
    return candidates_by_tag[0][1]


def _docker_image_id(image_ref: str) -> str:
    """Get Docker image ID (sha256:...) or 'unknown'"""
    try:
        out = subprocess.check_output(
            ["docker", "inspect", "--format", "{{.Id}}", image_ref], stderr=subprocess.STDOUT, text=True
        ).strip()
        return out if out.startswith("sha256:") else "unknown"
    except Exception:
        return "unknown"


def _resolve_image_ref(ref: str, *, build: bool = False) -> str:
    """
    Resolve image reference:
      - If build=True: use newest timestamped build tag
      - Else select platform-specific image from embedded registry (skip placeholders).
    """
    if build:
        return _get_newest_build_tag(ref)

    registry = _load_registry_for_ref(ref)
    platforms = (registry.get("image") or {}).get("platforms") or {}
    default_platform = (registry.get("image") or {}).get("default_platform", "amd64")
    arch = _detect_arch()

    # Prefer host arch if available and not a placeholder
    def _valid(v: str | None) -> bool:
        return bool(v) and "REPLACE_" not in v.upper()

    cand = platforms.get(arch)
    if _valid(cand):
        return cand

    # Fall back to default platform
    cand = platforms.get(default_platform)
    if _valid(cand):
        return cand

    raise ValueError(f"No valid image mapping for {ref}; platforms keys={list(platforms.keys())}")


# --- Local docker lifecycle ---------------------------------------------------
def _docker_available() -> bool:
    try:
        subprocess.run(["docker", "version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)  # noqa: S603
        return True
    except Exception:
        return False


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_port(host: str, port: int, budget_s: float) -> None:
    deadline = time.monotonic() + budget_s
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.25):
                return
        except OSError:
            time.sleep(0.05)
    raise TimeoutError(f"port {host}:{port} not open after {budget_s}s")


def _wait_healthy(session: requests.Session, base_url: str, health_path: str, budget_s: float) -> None:
    url = base_url.rstrip("/") + (health_path or "/healthz")
    backoff = 0.1
    deadline = time.monotonic() + budget_s
    while time.monotonic() < deadline:
        try:
            r = session.get(url, timeout=1.5)
            if r.status_code == 200 and (r.headers.get("content-type", "").startswith("application/json")):
                body = r.json()
                if isinstance(body, dict) and body.get("ok") is True:
                    return
        except Exception:
            pass
        time.sleep(backoff)
        backoff = min(backoff * 1.6, 1.5)
    raise TimeoutError(f"health check failed for {url}")


# --- Adapter ------------------------------------------------------------------
class LocalHTTPAdapter:
    def __init__(self, http: BaseHTTPAdapter | None = None) -> None:
        self._http = http or BaseHTTPAdapter()
        self._session = requests.Session()

    def invoke_by_ref(self, *, ref: str, payload: Dict[str, Any], **options) -> InvokeResult:
        local_opts = LocalInvokeOptions.from_ref(ref, **options)
        return self.invoke(payload=payload, options=local_opts, ref=ref)

    def invoke(self, *, payload: Dict[str, Any], options: LocalInvokeOptions, ref: str | None = None) -> InvokeResult:
        if not _docker_available():
            env = _error_envelope(payload.get("execution_id", ""), "ERR_DOCKER", "docker not available")
            return InvokeResult(status="error", envelope=env, http_status=0, url="")

        # Host URL and docker command
        port = _pick_free_port()
        base_url = f"http://127.0.0.1:{port}"
        start_cmd = ["docker", "run", "--rm", "-p", f"{port}:8000"]

        # Mount artifacts (optional)
        if options.mount_artifacts:
            start_cmd += ["-v", f"{options.mount_artifacts}:/artifacts:rw"]

        # IMAGE_DIGEST env: prefer expected_oci digest, else digest from image ref, else local image ID
        expected = _normalize_digest(options.expected_oci)
        fallback = _normalize_digest(options.image_ref)
        if expected:
            image_digest = expected
        elif fallback:
            image_digest = fallback
        else:
            # Local build: get Docker image ID
            image_digest = _docker_image_id(options.image_ref or "")
        start_cmd += ["-e", f"IMAGE_DIGEST={image_digest}"]

        # Image
        image = options.image_ref or (ref and _resolve_image_ref(ref)) or ""
        if not image:
            env = _error_envelope(payload.get("execution_id", ""), "ERR_IMAGE_NOT_FOUND", "no image reference resolved")
            return InvokeResult(status="error", envelope=env, http_status=0, url=base_url)
        start_cmd.append(image)

        # Start container
        info("adapter.local.container.start", cmd=" ".join(shlex.quote(c) for c in start_cmd), port=port, image=image)
        try:
            proc = subprocess.Popen(  # noqa: S603
                start_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
        except FileNotFoundError as fe:
            env = _error_envelope(payload.get("execution_id", ""), "ERR_DOCKER", f"docker not found: {fe}")
            return InvokeResult(status="error", envelope=env, http_status=0, url=base_url)

        # Wait for readiness
        try:
            _wait_for_port("127.0.0.1", port, budget_s=5.0)
            _wait_healthy(self._session, base_url, options.health_path, budget_s=15.0)
            info("adapter.health.ok", url=base_url + options.health_path)
        except Exception as e:
            stderr_tail = ""
            try:
                if proc.poll() is None:
                    time.sleep(0.25)
                if proc.stderr:
                    stderr_tail = "".join(proc.stderr.readlines()[-20:])
            except Exception:
                pass
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except Exception:
                proc.kill()
            error(
                "adapter.health.fail", url=base_url + options.health_path, err=str(e), stderr_tail=stderr_tail[-2000:]
            )
            env = _error_envelope(
                payload.get("execution_id", ""), "ERR_HEALTH", "unhealthy", {"stderr_tail": stderr_tail[-2000:]}
            )
            return InvokeResult(status="error", envelope=env, http_status=0, url=base_url)

        # Invoke over HTTP
        try:
            result = self._http.invoke(
                url=base_url,
                payload=payload,
                options=InvokeOptions(
                    expected_oci=options.expected_oci,
                    timeout_s=options.timeout_s,
                    run_path=options.run_path,
                    health_path=options.health_path,
                ),
            )
        finally:
            # Always stop the container
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

        return result
