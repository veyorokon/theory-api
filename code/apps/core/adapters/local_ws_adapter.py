# code/apps/core/adapters/local_ws_adapter.py
from __future__ import annotations
import os
import random
import socket
import subprocess
import time
from typing import Any, Dict, Iterator, Optional, Union

import httpx

from .base_ws_adapter import BaseWsAdapter, WsError
from ..utils.adapters import _normalize_digest, _docker_image_id


def _pick_port() -> int:
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


class LocalWsAdapter(BaseWsAdapter):
    """
    Starts the local container, waits for /healthz, then connects to ws://127.0.0.1:<port>/run
    Responsibilities:
      - image selection/build is done by the caller (oci["image_ref"])
      - we only 'docker run' with proper --user and mounts
    """

    def __init__(self, *args, mount_dir: str | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.mount_dir = mount_dir or os.getenv("THEORY_WORLD_DIR") or os.getcwd()

    def invoke(
        self,
        ref: str,
        payload: Dict[str, Any],
        timeout_s: int,
        oci: Dict[str, Any],
        stream: bool = False,
    ) -> Dict[str, Any] | Iterator[Dict[str, Any]]:
        """
        oci fields:
          - image_ref: "theory-local/ns-name:build-169.." or "<repo>@sha256:.."
          - expected_digest: sha256:...
          - env: dict[str,str] (IMAGE_DIGEST, etc.)
        """
        image_ref = oci.get("image_ref")
        expected_digest = oci.get("expected_digest")
        run_env = dict(oci.get("env") or {})
        if not image_ref:
            raise WsError("LocalWsAdapter requires oci.image_ref")

        host_port = _pick_port()
        ws_url = f"ws://127.0.0.1:{host_port}/run"

        uid = os.getuid() if hasattr(os, "getuid") else 1000
        gid = os.getgid() if hasattr(os, "getgid") else 1000

        # Ensure minimal env (determinism & required)
        run_env.setdefault("TZ", "UTC")
        run_env.setdefault("LC_ALL", "C.UTF-8")

        # IMAGE_DIGEST env: prefer expected_oci digest, else digest from image ref, else local image ID
        expected = _normalize_digest(expected_digest)
        fallback = _normalize_digest(image_ref)
        if expected:
            image_digest = expected
        elif fallback:
            image_digest = fallback
        else:
            # Local build: get Docker image ID
            image_digest = _docker_image_id(image_ref or "")
        run_env["IMAGE_DIGEST"] = image_digest

        docker_cmd = [
            "docker",
            "run",
            "--rm",
            "--user",
            f"{uid}:{gid}",
            "--network",
            "theory_api_app_network",
            "--add-host",
            "localhost:host-gateway",
        ]

        # Add all environment variables from run_env
        for key, value in run_env.items():
            docker_cmd.extend(["-e", f"{key}={value}"])

        # Add standard container environment variables
        docker_cmd.extend(
            [
                "-e",
                "HOME=/home/app",
                "-e",
                "XDG_CACHE_HOME=/home/app/.cache",
                "-e",
                "HF_HOME=/home/app/.cache/huggingface",
                "-p",
                f"{host_port}:8000",
                "-v",
                f"{self.mount_dir}:/world",
                image_ref,
            ]
        )

        # Redact secrets from docker command for logging
        def _redact_secrets(cmd_list, secret_keys):
            redacted_cmd = []
            i = 0
            while i < len(cmd_list):
                if cmd_list[i] == "-e" and i + 1 < len(cmd_list):
                    env_var = cmd_list[i + 1]
                    key = env_var.split("=", 1)[0]
                    if key in secret_keys:
                        redacted_cmd.extend(["-e", f"{key}=***"])
                    else:
                        redacted_cmd.extend([cmd_list[i], env_var])
                    i += 2
                else:
                    redacted_cmd.append(cmd_list[i])
                    i += 1
            return redacted_cmd

        # Get secret keys for redaction (anything that's not standard env vars)
        standard_keys = {"TZ", "LC_ALL", "IMAGE_DIGEST", "HOME", "XDG_CACHE_HOME", "HF_HOME"}
        secret_keys = set(run_env.keys()) - standard_keys
        redacted_cmd = _redact_secrets(docker_cmd, secret_keys)

        self.logger(event="docker.run", ref=ref, cmd=" ".join(redacted_cmd))
        proc = subprocess.Popen(docker_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            # Poll /healthz
            base = f"http://127.0.0.1:{host_port}"
            client = httpx.Client(timeout=1.5)
            deadline = time.time() + 30
            while time.time() < deadline:
                try:
                    r = client.get(f"{base}/healthz")
                    if r.status_code == 200:
                        break
                except Exception:
                    pass
                time.sleep(0.2)
            else:
                # Show a bit of logs on failure
                try:
                    err_tail = (proc.stderr.read() or b"").decode("utf-8", "replace")[-2000:]
                except Exception:
                    err_tail = ""
                raise WsError(f"Processor not healthy on port {host_port}. Logs tail:\n{err_tail}")

            # Delegate to base over WS
            oci2 = {"ws_url": ws_url, "headers": {}, "expected_digest": expected_digest}
            return super().invoke(ref, payload, timeout_s, oci2, stream=stream)

        finally:
            # Always attempt to stop container
            try:
                proc.terminate()
            except Exception:
                pass
