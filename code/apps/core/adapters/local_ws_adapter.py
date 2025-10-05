# code/apps/core/adapters/local_ws_adapter.py
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, Iterator

import httpx

from .base_ws_adapter import BaseWsAdapter, WsError


# Port state file location (must match localctl.py)
PORT_STATE_FILE = Path(__file__).parent.parent.parent.parent / ".theory" / "local_ports.json"


class LocalWsAdapter(BaseWsAdapter):
    """
    Pure connection adapter for local tools.

    Expects container already started via `localctl start --ref <ref>`.
    Mirrors ModalWsAdapter pattern: just connects to existing endpoint.

    Responsibilities:
      - Resolve port from localctl state file
      - Connect to ws://127.0.0.1:<port>/run
      - Delegate to base adapter for WebSocket protocol
    """

    def _resolve_port(self, ref: str) -> int:
        """
        Resolve assigned port for tool from localctl state file.

        Raises WsError if port not found (container not started).
        """
        if not PORT_STATE_FILE.exists():
            raise WsError(
                f"No port state file found. Start container with: python manage.py localctl start --ref {ref}"
            )

        try:
            with open(PORT_STATE_FILE) as f:
                state = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            raise WsError(f"Could not read port state file: {e}")

        if ref not in state:
            raise WsError(
                f"No port assigned for {ref}. Start container with: python manage.py localctl start --ref {ref}"
            )

        return state[ref]

    def invoke(
        self,
        ref: str,
        payload: Dict[str, Any],
        timeout_s: int,
        oci: Dict[str, Any],
        stream: bool = False,
    ) -> Dict[str, Any] | Iterator[Dict[str, Any]]:
        """
        Connect to already-running local container.

        oci fields:
          - expected_digest: sha256:... (for drift detection)
          - Headers/auth not needed for local

        Expects: `localctl start --ref {ref}` already called
        """
        expected_digest = oci.get("expected_digest")

        # Resolve port from localctl state file
        host_port = self._resolve_port(ref)
        ws_url = f"ws://127.0.0.1:{host_port}/run"

        # Check container is healthy before connecting
        import time

        base = f"http://127.0.0.1:{host_port}"
        client = httpx.Client(timeout=1.5)
        deadline = time.time() + 10  # 10s timeout for already-running container

        healthy = False
        for _ in range(20):
            try:
                r = client.get(f"{base}/healthz")
                if r.status_code == 200:
                    healthy = True
                    break
            except Exception:
                pass
            time.sleep(0.5)

        if not healthy:
            raise WsError(
                f"Container for {ref} not healthy on port {host_port}. "
                f"Start container with: python manage.py localctl start --ref {ref}"
            )

        # Delegate to base WebSocket adapter
        oci2 = {"ws_url": ws_url, "headers": {}, "expected_digest": expected_digest}
        return super().invoke(ref, payload, timeout_s, oci2, stream=stream)
