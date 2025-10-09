# code/apps/core/adapters/modal_ws_adapter.py
from __future__ import annotations
from typing import Any, Dict, Iterator, Optional, Union

from django.conf import settings

from .base_ws_adapter import BaseWsAdapter, WsError


class ModalWsAdapter(BaseWsAdapter):
    """
    WebSocket adapter for Modal-deployed tools.
    Resolves deployed function URL via Modal SDK.
    Modal always runs linux/amd64.
    """

    def invoke_run(self, run) -> Dict[str, Any]:
        """Override to force amd64 digest selection for Modal."""
        from apps.tools.models import Tool

        try:
            tool = Tool.objects.get(ref=run.ref)
        except Tool.DoesNotExist:
            raise WsError(f"Tool not found: {run.ref}")

        # Modal always runs amd64
        expected_digest = tool.digest_amd64

        # Build payload with presigned URLs
        payload = self._build_payload(run)

        # Invoke with Modal-resolved URL
        oci = {"expected_digest": expected_digest}
        return self.invoke(run.ref, payload, tool.timeout_s, oci, stream=False)

    def invoke(
        self,
        ref: str,
        payload: Dict[str, Any],
        timeout_s: int,
        oci: Dict[str, Any],
        stream: bool = False,
    ) -> Dict[str, Any] | Iterator[Dict[str, Any]]:
        from apps.core.management.commands._modal_common import modal_app_name
        from apps.core.utils.adapters import _get_modal_web_url

        # Resolve app name from ref and environment settings
        app_name = modal_app_name(
            ref,
            env=settings.APP_ENV,
            branch=settings.GIT_BRANCH,
            user=settings.GIT_USER,
        )

        # Get deployed URL via Modal SDK
        base_url = _get_modal_web_url(app_name).rstrip("/")
        expected_digest = oci.get("expected_digest")
        headers = dict(oci.get("headers") or {})

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
