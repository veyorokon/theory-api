# code/apps/core/orchestrator_ws.py
from __future__ import annotations
import json
import os
import time
import uuid
from typing import Any, Dict, Iterator, Optional, Tuple, Union, List

# Adapters (from the files you added)
from apps.core.adapters.base_ws_adapter import BaseWsAdapter, WsError
from apps.core.adapters.local_ws_adapter import LocalWsAdapter
from apps.core.adapters.modal_ws_adapter import ModalWsAdapter

# Existing services
from apps.storage.service import storage_service
from apps.core.registry.loader import load_processor_spec
from apps.core.utils.adapters import _get_newest_build_tag, _load_registry_for_ref

# --- Logging (use project logger if available; fall back to stdlib) ----------
try:
    from libs.runtime_common.logging import info, warn, error, debug  # type: ignore
except Exception:  # pragma: no cover
    import logging

    _L = logging.getLogger("orchestrator.ws")
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    def info(event: str, **fields):
        _L.info(json.dumps({"event": event, **fields}))

    def warn(event: str, **fields):
        _L.warning(json.dumps({"event": event, **fields}))

    def error(event: str, **fields):
        _L.error(json.dumps({"event": event, **fields}))

    def debug(event: str, **fields):
        _L.debug(json.dumps({"event": event, **fields}))


class OrchestratorWsError(RuntimeError):
    pass


class OrchestratorWS:
    """
    WebSocket orchestrator for processors.

    Responsibilities:
      - Resolve ref -> registry entry
      - Choose lane: --build=true (local built image) vs --build=false (pinned digest)
      - Prepare write_prefix and presigned PUT URLs for declared outputs + outputs.json
      - Open WS (Local or Modal adapter), send RunInvoke, stream live events or return final envelope
      - Enforce digest drift checks and index discipline
    """

    def __init__(self, *, default_bucket: str = None):
        if default_bucket is None:
            from django.conf import settings

            storage = getattr(settings, "STORAGE", {})
            default_bucket = storage.get("BUCKET", "outputs")
        self.bucket = default_bucket

    # ---------- Public API ----------

    def invoke(
        self,
        *,
        ref: str,  # ns/name@ver
        mode: str,  # "mock" | "real"
        inputs: Dict[str, Any],
        build: bool,  # True => build lane; False => pinned lane
        stream: bool,  # True => iterator of events; False => final envelope
        settle: str = "fast",
        timeout_s: int = 600,
        execution_id: str | None = None,
        write_prefix: str | None = None,
        world_facet: str = "artifacts",  # usually "artifacts"
        adapter: str = "local",  # "local" | "modal"
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
            raise OrchestratorWsError(f"Unknown processor ref: {ref}")

        # All processors now use WebSocket protocol (standardized)

        outputs_decl = reg.get("outputs") or []
        # 2) Compute execution + prefix
        eid = execution_id or str(uuid.uuid4())
        if write_prefix:
            wprefix = write_prefix
        else:
            # Parse ref into canonical namespace/name@version structure
            ns, name_with_ver = ref.split("/", 1)
            name, ver = name_with_ver.split("@")
            wprefix = f"/{world_facet}/{ns}/{name}/{ver}/{eid}/"

        if "{execution_id}" in wprefix:
            wprefix = wprefix.replace("{execution_id}", eid)
        if not wprefix.endswith("/"):
            wprefix += "/"

        # Guard against outputs duplication
        assert not wprefix.rstrip("/").endswith("/outputs"), f"write_prefix must not contain '/outputs': {wprefix}"

        # 3) Choose lane: build vs pinned, and target adapter
        if build:
            image_ref, expected_digest, target = self._lane_build(ref, reg, adapter)
        else:
            image_ref, expected_digest, target = self._lane_pinned(ref, reg, adapter, platform)

        # 4) Prepare presigned PUTs for durability (declared outputs + outputs.json)
        put_urls = self._prepare_put_urls(wprefix, outputs_decl)

        # 5) Resolve required secrets based on mode
        required_secrets = (reg.get("secrets") or {}).get("required", [])
        env = {}
        if mode == "real":
            from apps.core.integrations.secret_resolver import resolve_secret

            for secret_name in required_secrets:
                secret_value = resolve_secret(secret_name)
                if not secret_value:
                    raise OrchestratorWsError(f"Missing required secret: {secret_name}")
                env[secret_name] = secret_value

        # 6) Construct payload (same shape as your HTTP body, plus put_urls)
        payload = {
            "execution_id": eid,
            "mode": mode,
            "inputs": inputs,
            "write_prefix": wprefix,
            "put_urls": put_urls,
            "settle": settle,
        }

        # 7) Pick adapter (local vs modal)
        adapter, oci = self._pick_adapter(target, image_ref, expected_digest, reg, env)

        # 7) Invoke over WS
        info("invoke.ws.start", ref=ref, target=target, build=build, eid=eid, write_prefix=wprefix)
        if stream:
            # Streaming iterator (yield events and final RunResult)
            return adapter.invoke(ref, payload, timeout_s, oci, stream=True)
        else:
            # Final envelope only
            env = adapter.invoke(ref, payload, timeout_s, oci, stream=False)
            info("invoke.ws.settle", ref=ref, status=env.get("status"), eid=eid)
            return env

    # ---------- Lanes ----------

    def _lane_build(self, ref: str, reg: Dict[str, Any], adapter: str) -> Tuple[str, str | None, str]:
        """
        Build-from-source lane: returns (image_ref, expected_digest, target)
          - For local: image_ref is local built tag, target="local"
          - For modal: not supported in build lane, should fail
        """
        if adapter == "modal":
            raise OrchestratorWsError("Modal adapter does not support build lane. Use --build=false for pinned lane.")

        image_ref = _get_newest_build_tag(ref)  # should return the built tag
        expected_digest = None  # do not enforce registry digest in build lane
        return image_ref, expected_digest, "local"

    def _lane_pinned(
        self, ref: str, reg: Dict[str, Any], adapter: str, platform: str | None = None
    ) -> Tuple[str, str | None, str]:
        """
        Pinned lane: returns (image_ref_or_base_url, expected_digest, target)
          - For local pinned: use registry digest to select image, target="local"
          - For Modal: return modal base URL + expected_digest, target="modal"

        Args:
            platform: Override platform for digest selection. If None, defaults to amd64 for modal, host platform for local
        """
        if adapter == "modal":
            # For Modal, we need to resolve the base URL from deployment
            try:
                from apps.core.utils.adapters import _normalize_digest

                # Extract expected digest from registry
                image = reg.get("image") or {}
                platforms = image.get("platforms") or {}
                # Modal always runs amd64 unless explicitly overridden
                default_platform = platform or "amd64"
                registry_digest = platforms.get(default_platform)
                expected_digest = _normalize_digest(registry_digest)

                # Resolve Modal base URL from deployed app
                base_url = self._resolve_modal_base_url(ref)

                return base_url, expected_digest, "modal"
            except Exception as e:
                raise OrchestratorWsError(f"Could not resolve Modal deployment for {ref}: {e}")
        else:
            # Local pinned lane with registry digest
            try:
                from apps.core.utils.adapters import _get_newest_build_tag, _normalize_digest

                image_ref = _get_newest_build_tag(ref)

                # Extract expected digest from registry
                image = reg.get("image") or {}
                platforms = image.get("platforms") or {}
                # Use provided platform or detect from host
                default_platform = platform or self._host_platform()
                registry_digest = platforms.get(default_platform)
                expected_digest = _normalize_digest(registry_digest)

                return image_ref, expected_digest, "local"
            except Exception as e:
                raise OrchestratorWsError(f"Could not resolve pinned image for {ref}: {e}")

    # ---------- Presigned PUT helpers ----------

    def _prepare_put_urls(self, write_prefix: str, outputs_decl: List[Dict[str, Any]]) -> Dict[str, str]:
        """
        Produce presigned PUT URLs for:
          - outputs.json (index, always at write_prefix/outputs.json)
          - each declared output path (relative to outputs/)
        Keys in the dict are OBJECT KEYS relative to bucket root, matching what the processor will write.
        """
        put_urls: Dict[str, str] = {}
        # Index last
        index_key = self._key(write_prefix, "outputs.json")
        put_urls["outputs.json"] = self._presign_put(index_key, content_type="application/json")

        # Declared outputs
        for o in outputs_decl:
            rel = o.get("path")
            if not rel:
                continue
            key = self._key(write_prefix, f"outputs/{rel}")
            ctype = o.get("mime") or "application/octet-stream"
            put_urls[f"outputs/{rel}"] = self._presign_put(key, content_type=ctype)
        return put_urls

    def _key(self, write_prefix: str, tail: str) -> str:
        """
        Convert logical write_prefix + tail into an object key under the bucket.
        - If write_prefix begins with "/artifacts/", strip the leading slash to form the key
        """
        # Normalize leading slash; you can map world facet to real bucket prefixes if needed
        path = write_prefix
        if path.startswith("/"):
            path = path[1:]
        if not path.endswith("/"):
            path += "/"
        return f"{path}{tail}"

    def _presign_put(self, key: str, *, content_type: str | None = None, expires_s: int = 900) -> str:
        # Use the existing get_upload_url method from storage service
        return storage_service.get_upload_url(
            bucket=self.bucket, key=key, expires_in=expires_s, content_type=content_type
        )

    # ---------- Adapter selection ----------

    def _pick_adapter(
        self, target: str, image_ref_or_base: str, expected_digest: str | None, reg: Dict[str, Any], env: Dict[str, str]
    ):
        """
        Returns (adapter_instance, oci_dict)
        """
        if target == "local":

            def log_fn(event: str, **fields):
                info(event, **fields)

            adapter = LocalWsAdapter(logger=log_fn)

            oci = {
                "image_ref": image_ref_or_base,
                "expected_digest": expected_digest,
                "env": env,  # Include resolved secrets
            }
            return adapter, oci
        elif target == "modal":

            def log_fn(event: str, **fields):
                info(event, **fields)

            adapter = ModalWsAdapter(logger=log_fn)
            headers = {}
            # Skip ticket service for now - not implemented yet
            oci = {
                "base_url": image_ref_or_base,  # modal base
                "expected_digest": expected_digest,
                "headers": headers,
            }
            return adapter, oci
        else:
            raise OrchestratorWsError(f"Unknown target: {target}")

    # ---------- Utilities ----------

    def _host_platform(self) -> str:
        # crude: let registry pick; fallback based on arch
        import platform

        return "arm64" if platform.machine().lower() in ("arm64", "aarch64") else "amd64"

    def _resolve_modal_base_url(self, ref: str) -> str:
        """Resolve Modal deployment web URL for a processor ref."""
        from apps.core.management.commands._modal_common import modal_app_name, _guess_user, _guess_branch
        from apps.core.utils.adapters import _get_modal_web_url
        from django.conf import settings

        # Get Modal context from Django settings or environment
        env = getattr(settings, "MODAL_ENVIRONMENT", "dev")
        user = getattr(settings, "MODAL_USER", None) or _guess_user()
        branch = getattr(settings, "MODAL_BRANCH", None) or _guess_branch()

        # Generate the canonical app name
        if env == "dev":
            app_name = modal_app_name(ref, env=env, branch=branch, user=user)
        else:
            app_name = modal_app_name(ref, env=env)

        # Resolve the web URL from Modal deployment
        base_url = _get_modal_web_url(app_name, "fastapi_app")

        return base_url
