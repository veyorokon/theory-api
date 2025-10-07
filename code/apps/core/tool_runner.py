# code/apps/core/tool_runner.py
"""
Direct tool execution without persistence.
Used by localctl/modalctl for ephemeral CLI runs.
For persisted runs, use RunService instead.
"""

from __future__ import annotations
import json
import os
import time
import uuid
from typing import Any, Dict, Iterator, Optional, Tuple, Union, List

# Adapters
from apps.core.adapters.base_ws_adapter import BaseWsAdapter, WsError
from apps.core.adapters.local_ws_adapter import LocalWsAdapter
from apps.core.adapters.modal_ws_adapter import ModalWsAdapter

# Services
from backend.storage.service import storage_service
from apps.core.registry.loader import load_processor_spec
from apps.core.utils.adapters import _get_newest_build_tag, _load_registry_for_ref

# --- Logging (use project logger if available; fall back to stdlib) ----------
try:
    from libs.runtime_common.logging import info, warn, error, debug  # type: ignore
except Exception:  # pragma: no cover
    import logging

    _L = logging.getLogger("tool_runner")
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    def info(event: str, **fields):
        _L.info(json.dumps({"event": event, **fields}))

    def warn(event: str, **fields):
        _L.warning(json.dumps({"event": event, **fields}))

    def error(event: str, **fields):
        _L.error(json.dumps({"event": event, **fields}))

    def debug(event: str, **fields):
        _L.debug(json.dumps({"event": event, **fields}))


class ToolRunnerError(RuntimeError):
    pass


class ToolRunner:
    """
    Direct tool execution without persistence.

    Responsibilities:
      - Resolve ref -> registry entry
      - Resolve image digest from registry
      - Prepare write_prefix and presigned PUT URLs for declared outputs + outputs.json
      - Open WS (Local or Modal adapter), send RunInvoke, stream live events or return final envelope
      - Enforce digest drift checks and index discipline

    Note: Containers must be started/deployed before invoking (use localctl/modalctl start).
    """

    def __init__(self, *, default_bucket: str = None):
        if default_bucket is None:
            from django.conf import settings

            storage = settings.STORAGE
            default_bucket = storage.get("BUCKET", "outputs")
        self.bucket = default_bucket

    # ---------- Public API ----------

    def invoke(
        self,
        *,
        ref: str,  # ns/name@ver
        mode: str,  # "mock" | "real"
        inputs: Dict[str, Any],
        stream: bool,  # True => iterator of events; False => final envelope
        timeout_s: int = 600,
        run_id: str | None = None,
        adapter: str = "local",  # "local" | "modal"
        artifact_scope: str,  # "world" | "local" - where artifacts are written
        platform: str
        | None = None,  # Override platform for digest selection (default: host platform or amd64 for modal)
    ) -> Dict[str, Any] | Iterator[Dict[str, Any]]:
        """
        Returns:
          - if stream=False: final envelope dict
          - if stream=True: iterator yielding WS events (Token|Frame|Log|Event) and finally a RunResult
        """
        # 1) Resolve registry
        try:
            reg = load_processor_spec(ref)  # must include image digests, outputs list, api info
        except FileNotFoundError:
            raise ToolRunnerError(f"Unknown tool ref: {ref}")

        # All tools now use WebSocket protocol (standardized)

        outputs_decl = reg.get("outputs") or {}
        # 2) Compute run_id
        rid = run_id or str(uuid.uuid4())

        # Compute ref_slug for storage namespacing: llm/litellm@1 → llm_litellm
        ref_slug = ref.split("@", 1)[0].replace("/", "_")

        # 3) Extract expected digest from registry (for drift validation)
        expected_digest = self._get_expected_digest(reg, adapter, platform)

        # 4) Prepare outputs map based on artifact_scope
        # artifact_scope="world" → generate presigned URLs for S3 upload
        # artifact_scope="local" → omit outputs, protocol writes to /artifacts/
        outputs_map = None
        if artifact_scope == "world":
            outputs_map = self._prepare_put_urls(ref_slug, rid, outputs_decl)

        # 5) Construct payload (flattened - no nested payload wrapper)
        # Note: Secrets are managed separately:
        #   - local: injected by localctl start
        #   - modal: synced by modalctl sync-secrets
        payload = {
            "run_id": rid,
            "mode": mode,
            "inputs": inputs,
        }

        # Only include outputs if artifact_scope="world"
        if outputs_map is not None:
            payload["outputs"] = outputs_map

        # 6) Pick adapter (local vs modal)
        adapter_instance, oci = self._pick_adapter(adapter, expected_digest, ref, reg)

        # 7) Invoke over WS
        info("invoke.ws.start", ref=ref, adapter=adapter, run_id=rid)
        if stream:
            # Streaming iterator (yield events and final RunResult)
            return adapter_instance.invoke(ref, payload, timeout_s, oci, stream=True)
        else:
            # Final envelope only
            env = adapter_instance.invoke(ref, payload, timeout_s, oci, stream=False)
            info("invoke.ws.complete", ref=ref, status=env.get("status"), run_id=rid)
            return env

    # ---------- Digest resolution ----------

    def _get_expected_digest(self, reg: Dict[str, Any], adapter: str, platform: str | None = None) -> str | None:
        """
        Extract expected digest from registry for drift validation.

        Args:
            platform: Override platform for digest selection. If None, defaults to amd64 for modal, host platform for local

        Returns:
            sha256:... digest if found in registry, None otherwise (skips drift check)
        """
        from apps.core.utils.adapters import _normalize_digest

        image = reg.get("image") or {}
        platforms = image.get("platforms") or {}

        # Modal always runs amd64 unless explicitly overridden, local uses host platform
        if adapter == "modal":
            default_platform = platform or "amd64"
        else:
            default_platform = platform or self._host_platform()

        registry_digest = platforms.get(default_platform)
        return _normalize_digest(registry_digest)

    # ---------- Presigned PUT helpers ----------

    def _prepare_put_urls(self, ref_slug: str, run_id: str, outputs_decl: Dict[str, Any]) -> Dict[str, str]:
        """
        Produce presigned PUT URLs for declared outputs.
        Keys in dict match registry output keys (e.g., "response", "usage").
        S3 path: artifacts/outputs/{ref_slug}/{run_id}/{output_key}
        """
        put_urls: Dict[str, str] = {}
        properties = outputs_decl.get("properties") or {}

        for output_key, spec in properties.items():
            # S3 key: artifacts/outputs/llm_litellm/abc-123/response
            s3_key = f"artifacts/outputs/{ref_slug}/{run_id}/{output_key}"
            ctype = spec.get("mime") or "application/octet-stream"
            put_urls[output_key] = self._presign_put(s3_key, content_type=ctype)

        return put_urls

    def _presign_put(self, key: str, *, content_type: str | None = None, expires_s: int = 900) -> str:
        # Use the existing get_upload_url method from storage service
        return storage_service.get_upload_url(
            bucket=self.bucket, key=key, expires_in=expires_s, content_type=content_type
        )

    # ---------- Adapter selection ----------

    def _pick_adapter(
        self,
        adapter: str,
        expected_digest: str | None,
        ref: str,
        reg: Dict[str, Any],
    ):
        """
        Returns (adapter_instance, oci_dict)

        Note: Containers must already be running (localctl start) or deployed (modalctl start).
        """

        def log_fn(event: str, **fields):
            info(event, **fields)

        if adapter == "local":
            adapter_instance = LocalWsAdapter(logger=log_fn)
            oci = {
                "expected_digest": expected_digest,
                # Note: Container must be started via localctl before invoking
            }
            return adapter_instance, oci

        elif adapter == "modal":
            # Resolve Modal deployment base URL
            try:
                base_url = self._resolve_modal_base_url(ref)
            except Exception as e:
                raise ToolRunnerError(f"Could not resolve Modal deployment for {ref}: {e}")

            adapter_instance = ModalWsAdapter(logger=log_fn)
            headers = {}
            # Skip ticket service for now - not implemented yet
            oci = {
                "base_url": base_url,
                "expected_digest": expected_digest,
                "headers": headers,
            }
            return adapter_instance, oci

        else:
            raise ToolRunnerError(f"Unknown adapter: {adapter}")

    # ---------- Utilities ----------

    def _host_platform(self) -> str:
        # crude: let registry pick; fallback based on arch
        import platform

        return "arm64" if platform.machine().lower() in ("arm64", "aarch64") else "amd64"

    def _resolve_modal_base_url(self, ref: str) -> str:
        """Resolve Modal deployment web URL for a tool ref."""
        from apps.core.management.commands._modal_common import modal_app_name
        from apps.core.utils.adapters import _get_modal_web_url
        from django.conf import settings

        # Get Modal context from Django settings (required, no fallbacks)
        env = settings.MODAL_ENVIRONMENT
        user = settings.GIT_USER
        branch = settings.GIT_BRANCH

        # Generate the canonical app name
        if env == "dev":
            app_name = modal_app_name(ref, env=env, branch=branch, user=user)
        else:
            app_name = modal_app_name(ref, env=env)

        # Resolve the web URL from Modal deployment
        base_url = _get_modal_web_url(app_name, "fastapi_app")

        return base_url
