# code/apps/core/adapters/modal_ws_adapter.py
from __future__ import annotations
from typing import Any, Dict, Iterator, Optional, Union

from .base_ws_adapter import BaseWsAdapter, WsError


class ModalWsAdapter(BaseWsAdapter):
    """
    WebSocket adapter for Modal-deployed tools.
    Control plane must resolve the deployed base URL and digest.
      oci:
        - base_url: "https://your-tool.modal.run" (no trailing slash)
        - expected_digest: "sha256:..."
        - headers: {"Authorization": "Bearer <ticket>"}  # short-lived run ticket (optional but recommended)
    """

    def invoke(
        self,
        ref: str,
        payload: Dict[str, Any],
        timeout_s: int,
        oci: Dict[str, Any],
        stream: bool = False,
    ) -> Dict[str, Any] | Iterator[Dict[str, Any]]:
        base_url = (oci.get("base_url") or "").rstrip("/")
        expected_digest = oci.get("expected_digest")
        headers = dict(oci.get("headers") or {})

        if not base_url:
            raise WsError("ModalWsAdapter requires oci.base_url")

        # Normalize to wss and attach /run
        if base_url.startswith("http://"):
            ws_url = "ws://" + base_url[len("http://") :] + "/run"
        elif base_url.startswith("https://"):
            ws_url = "wss://" + base_url[len("https://") :] + "/run"
        elif base_url.startswith("ws://") or base_url.startswith("wss://"):
            ws_url = base_url + "/run"
        else:
            # assume host without scheme
            ws_url = "wss://" + base_url + "/run"

        oci2 = {"ws_url": ws_url, "headers": headers, "expected_digest": expected_digest}
        return super().invoke(ref, payload, timeout_s, oci2, stream=stream)
