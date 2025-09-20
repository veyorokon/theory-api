"""
Modal adapter (0021): tar-pull /work/out/**, canonicalize, upload, and return canonical envelope.

Contracts:
- Reads processor spec from registry (pinned digest required unless --build path is used elsewhere).
- Writes inputs.json to /work, invokes the processor entrypoint, tars /work/out, returns tar bytes.
- Canonicalizes names, rejects duplicates post-canon, computes cid/size/mime, sorts by path,
  writes /artifacts/execution/<id>/outputs.json as {"outputs":[...]} with compact separators,
  and returns a shared success envelope. Nested error envelope on failure.

Env/config (explicit only; no magic):
- settings.MODAL_ENABLED: bool (required True)
- settings.MODAL_ENVIRONMENT: str (e.g., "dev" | "main"), optional; informs app naming only
- Secrets are injected by *name* (from registry); values resolved by SecretResolver at dispatch time.
"""

from __future__ import annotations

import io
import json
import tarfile
import time
import traceback
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from django.conf import settings

from .base import RuntimeAdapter  # same base class used by local/mock
from .envelope import success_envelope, error_envelope, write_outputs_index  # shared serializers
from .modal.naming import modal_app_name_from_ref, modal_fn_name

# Storage & utils (world writes + cid + mime)
from apps.storage.service import storage_service
from apps.core.utils.env_fingerprint import (
    compose_env_fingerprint,
    collect_present_env_keys,
)  # utility in your codebase
from apps.core.utils.worldpath import canonicalize_worldpath, ERR_DECODED_SLASH, ERR_DOT_SEGMENTS
from apps.core.errors import ERR_IMAGE_UNPINNED, ERR_MISSING_SECRET, ERR_OUTPUT_DUPLICATE, ERR_ADAPTER_INVOCATION
from apps.core.utils.mime import guess_mime  # simple extension->mime helper
from libs.runtime_common.hashing import blake3_cid  # returns "b3:<hex>"

# Modal import guarded to keep import-time failures pretty
try:
    import modal

    _MODAL_AVAILABLE = True
except Exception:  # pragma: no cover
    _MODAL_AVAILABLE = False

# Default client-side timeout for Modal function calls
DEFAULT_CLIENT_TIMEOUT_S = 90


@dataclass(frozen=True)
class ModalAdapterOpts:
    timeout_s: int
    cpu: float
    memory_gb: float
    gpu: str | None = None  # 0021: usually None; 0022+ will set GPU
    snapshot: str = "off"  # "off" | "cpu" | "gpu"
    region: str | None = None
    presigned_push: bool = False  # 0021: must be False (tar-pull only)


class ModalAdapter(RuntimeAdapter):
    """
    Execute a processor inside Modal using the pinned OCI image digest.

    Flow:
    1) Validate Modal availability and processor spec.
    2) Build env_fingerprint (names-only for secrets).
    3) Invoke remote function (image=spec.image.oci digest), pass inputs JSON + write_prefix.
    4) Receive tar bytes of /work/out, canonicalize and upload to World.
    5) Write outputs index object {"outputs":[...]} and return success envelope.

    Errors return the nested error envelope (status="error", error{code,message}).
    """

    def __init__(self) -> None:
        super().__init__()

    def invoke(
        self,
        *,
        processor_ref: str,
        mode: str = "default",
        inputs_json: Dict[str, Any],
        write_prefix: str,
        execution_id: str,
        registry_snapshot: Dict[str, Any],
        adapter_opts: Dict[str, Any],
        secrets_present: List[str],
    ) -> Dict[str, Any]:
        t0 = time.time()

        # Guard: modal package / feature flag present
        if not getattr(settings, "MODAL_ENABLED", False) or not _MODAL_AVAILABLE:
            return self._err(
                execution_id,
                code=ERR_ADAPTER_INVOCATION,
                msg="Modal not available. Install 'modal' and set MODAL_ENABLED=True.",
            )

        # Resolve processor spec from registry snapshot
        try:
            spec = registry_snapshot["processors"][processor_ref]
            image_digest = spec["image"]["oci"]  # must contain @sha256:...
            if "@sha256:" not in image_digest:
                return self._err(
                    execution_id,
                    code=ERR_IMAGE_UNPINNED,
                    msg=f"Processor image not pinned by digest: {image_digest}",
                )
            runtime = spec.get("runtime", {}) or {}
            required_secrets: List[str] = []
            opt = spec.get("secrets", {})
            # Secrets schema variants tolerated: list or {required, optional}
            if isinstance(opt, dict):
                required_secrets = list(opt.get("required", []))
                optional_secrets = list(opt.get("optional", []))
            elif isinstance(opt, list):
                required_secrets = list(opt)
                optional_secrets = []
            else:
                required_secrets = []
                optional_secrets = []
        except Exception as e:
            return self._err(
                execution_id,
                code=ERR_ADAPTER_INVOCATION,
                msg=f"Failed to resolve processor spec: {e}",
            )

        # Validate required secrets are present by *name*
        missing = [s for s in required_secrets if s not in secrets_present]
        if missing:
            return self._err(
                execution_id,
                code=ERR_MISSING_SECRET,
                msg="Required secret(s) missing: " + ", ".join(missing),
            )

        # Adapter options (normalized)
        mad = self._normalize_opts(adapter_opts, runtime)
        if mad.presigned_push:
            # 0021: tar-pull only; presigned push lands in 0022
            return self._err(
                execution_id,
                code=ERR_ADAPTER_INVOCATION,
                msg="Presigned push is disabled in 0021; use tar-pull.",
            )

        # Build env_fingerprint (names only; never values)
        present_env_keys = collect_present_env_keys(
            base_keys=required_secrets + optional_secrets, additional_keys=secrets_present
        )
        env_fingerprint = compose_env_fingerprint(
            image_digest=image_digest,
            runtime={
                "cpu": mad.cpu,
                "memory_gb": mad.memory_gb,
                "timeout_s": mad.timeout_s,
                "gpu": mad.gpu or "none",
            },
            versions={},  # keep empty in 0021
            present_env_keys=present_env_keys,
            snapshot=mad.snapshot,
            region=mad.region,
            adapter="modal",
        )

        # Canonicalize write_prefix (facet-rooted, endswith '/')
        try:
            wp = self._canon_prefix(write_prefix)
        except ValueError as ve:
            return self._err(
                execution_id,
                code=ERR_ADAPTER_INVOCATION,
                msg=f"Write prefix validation failed: {ve}",
                env_fp=env_fingerprint,
            )

        # ---- Execute on Modal ----
        try:
            # Store spec for function naming
            self._current_spec = spec
            tar_bytes = self._modal_run_and_tar(
                processor_ref=processor_ref,
                mode=mode,
                inputs_json=inputs_json,
                write_prefix=wp,
                image_digest=image_digest,
                timeout_s=mad.timeout_s,
                required_secret_names=required_secrets + optional_secrets,
            )
        except Exception as e:
            tb = traceback.format_exc(limit=2)
            # Clamp error message to prevent huge envelopes, but include stderr tail from container
            error_msg = str(e)[:2000]
            return self._err(
                execution_id,
                code=ERR_ADAPTER_INVOCATION,
                msg=error_msg,
                env_fp=env_fingerprint,
                meta_extra={"traceback": tb},
            )

        # ---- Canonicalize outputs from tar and upload to World ----
        try:
            outputs, outputs_index_path = self._canonicalize_and_upload(
                tar_bytes=tar_bytes,
                write_prefix=wp,
                execution_id=execution_id,
            )
        except DuplicateTargetError as de:
            return self._err(execution_id, code=ERR_OUTPUT_DUPLICATE, msg=str(de), env_fp=env_fingerprint)
        except CanonicalizationError as ce:
            return self._err(
                execution_id,
                code=ERR_ADAPTER_INVOCATION,
                msg=f"Output canonicalization failed: {ce}",
                env_fp=env_fingerprint,
            )
        except Exception as e:
            return self._err(
                execution_id, code=ERR_ADAPTER_INVOCATION, msg=f"Output upload failed: {e}", env_fp=env_fingerprint
            )

        duration_ms = int((time.time() - t0) * 1000)

        # Success envelope
        return success_envelope(
            execution_id=execution_id,
            outputs=outputs,
            index_path=outputs_index_path,
            image_digest=image_digest,
            env_fingerprint=env_fingerprint,
            duration_ms=duration_ms,
        )

    # ---------------- internals ----------------

    def _normalize_opts(self, adapter_opts: Dict[str, Any], runtime: Dict[str, Any]) -> ModalAdapterOpts:
        def _num(x, default):
            try:
                return type(default)(x)
            except Exception:
                return default

        timeout_s = _num(adapter_opts.get("timeout_s", runtime.get("timeout_s", 300)), 300)
        cpu = float(adapter_opts.get("cpu", runtime.get("cpu", 1)))
        memory_gb = float(adapter_opts.get("memory_gb", runtime.get("memory_gb", 2)))
        gpu = adapter_opts.get("gpu", runtime.get("gpu"))
        snapshot = adapter_opts.get("snapshot", "off")
        region = adapter_opts.get("region")
        presigned_push = bool(adapter_opts.get("presigned_push", False))
        return ModalAdapterOpts(
            timeout_s=timeout_s,
            cpu=cpu,
            memory_gb=memory_gb,
            gpu=gpu,
            snapshot=snapshot,
            region=region,
            presigned_push=presigned_push,
        )

    def _canon_prefix(self, write_prefix: str) -> str:
        if not write_prefix.endswith("/"):
            raise ValueError("--write-prefix must end with '/'")
        p, err = canonicalize_worldpath(write_prefix)
        if err:
            if err in (ERR_DECODED_SLASH, ERR_DOT_SEGMENTS):
                raise ValueError(f"Invalid write_prefix: {err}")
            raise ValueError(f"Invalid write_prefix: {err}")
        # facet-root must be /artifacts/**
        if not p.startswith("/artifacts/"):
            raise ValueError("write_prefix must be under /artifacts/")
        return p

    def _function_name_from_spec(self, ref: str, spec: Dict[str, Any], mode: str = "default") -> str:
        """0021: functions are named 'run' in each app; keep API stable."""
        import os

        # Override function name based on mode
        if mode == "smoke":
            return os.getenv("MODAL_FUNCTION_NAME", "smoke")
        else:
            return os.getenv("MODAL_FUNCTION_NAME", modal_fn_name())

    def _app_name_from_ref(self, ref: str, env: str) -> str:
        """Generate Modal app name using shared naming logic."""
        return modal_app_name_from_ref(ref, env)

    def _call_modal_function(
        self, *, app_name: str, func_name: str, payload: Dict[str, Any], wait_s: int | None = None
    ) -> bytes:
        """Call Modal function with timeout-based fail-fast behavior."""
        if not _MODAL_AVAILABLE:
            raise RuntimeError("Modal SDK not available")

        # Function.from_name is the modern API
        fn = modal.Function.from_name(app_name, func_name)

        # Prefer spawn + get(timeout) to avoid indefinite waits even if function-level timeout is larger
        handle = fn.spawn(payload)
        try:
            timeout_val = wait_s or DEFAULT_CLIENT_TIMEOUT_S
            result = handle.get(timeout=timeout_val)
            return result
        except Exception:
            # Fast-path error surface: e will contain the RuntimeError message we raised inside the function
            # (includes exit code and stderr tail). Bubble it up to envelope builder.
            raise

    def _call_generated(
        self, env: str, func_name: str, payload: Dict[str, Any], *, app_name: str | None = None
    ) -> bytes:
        """Call pre-deployed Modal function by name using Function.from_name."""
        if not _MODAL_AVAILABLE:
            raise RuntimeError("Modal SDK not available")

        if not app_name:
            app_name = getattr(settings, "MODAL_APP_NAME", "theory-rt")

        try:
            from modal import Function as _Fn

            fn = _Fn.from_name(app_name, func_name, environment_name=env)
            handle = fn.spawn(payload)
            return handle.get(timeout=DEFAULT_CLIENT_TIMEOUT_S)
        except Exception as e:
            raise RuntimeError(
                f"Modal function '{func_name}' not found in app='{app_name}' env='{env}'. "
                f"Ensure deployment via: modal deploy --env {env} -m modal_app. Error: {e}"
            )

    def _modal_run_and_tar(
        self,
        *,
        processor_ref: str,
        mode: str = "default",
        inputs_json: Dict[str, Any],
        write_prefix: str,
        image_digest: str,
        timeout_s: int,
        required_secret_names: List[str],
    ) -> bytes:
        """
        Call pre-deployed Modal function to execute processor and return tar bytes.

        This uses pre-deployed Modal functions to enable warm container reuse and
        GPU memory snapshots. Functions must be deployed via sync_modal command.
        """
        if not _MODAL_AVAILABLE:
            raise RuntimeError("Modal SDK not available")

        # Store ref for error messages
        self._current_ref = processor_ref

        # Get environment and function name
        env = settings.MODAL_ENVIRONMENT or "dev"
        spec = self._current_spec  # Set by caller
        func_name = self._function_name_from_spec(processor_ref, spec, mode)
        app_name = self._app_name_from_ref(processor_ref, env)

        # Prepare payload for pre-deployed function
        payload = {"inputs_json": inputs_json, "write_prefix": write_prefix}

        # Call pre-deployed function
        return self._call_generated(env, func_name, payload, app_name=app_name)

    def _canonicalize_and_upload(
        self, *, tar_bytes: bytes, write_prefix: str, execution_id: str
    ) -> Tuple[List[Dict[str, Any]], str]:
        """
        Walk tar members, canonicalize names, detect duplicates post-canon, upload to World.
        Write outputs index as object: {"outputs":[...]} under /artifacts/execution/<id>/outputs.json.
        """
        outputs: List[Dict[str, Any]] = []

        dup_guard: set[str] = set()

        with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:gz") as tf:
            for m in tf.getmembers():
                if not m.isfile():
                    continue
                raw_rel = m.name  # relative within /work/out
                # Normalize to POSIX relpath; reject traversal
                if raw_rel.startswith("/") or ".." in raw_rel.split("/"):
                    raise CanonicalizationError(f"Illegal output path in tar: {raw_rel}")

                # Compose world path: write_prefix + normalized rel
                target_path = write_prefix + raw_rel

                # Canonicalize world path
                canon, err = canonicalize_worldpath(target_path)
                if err:
                    raise CanonicalizationError(f"Invalid output path {target_path}: {err}")

                # Duplicate-after-canon guard (case/percent/Unicode normalization already applied by canonicalizer)
                if canon in dup_guard:
                    raise DuplicateTargetError(f"Duplicate target after canonicalization: {canon}")
                dup_guard.add(canon)

                # Extract file bytes
                f = tf.extractfile(m)
                if not f:
                    continue
                data = f.read()

                # Compute cid/size/mime
                cid = blake3_cid(data)
                size_bytes = len(data)
                mime = guess_mime(canon)

                # Upload
                storage_service.write_file(canon, data, mime=mime)

                # Record output entry
                outputs.append({"path": canon, "cid": cid, "size_bytes": size_bytes, "mime": mime})

        # Write index with centralized helper
        index_path = f"/artifacts/execution/{execution_id}/outputs.json"
        index_bytes = write_outputs_index(index_path, outputs)
        storage_service.write_file(
            index_path,
            index_bytes,
            mime="application/json",
        )

        return outputs, index_path

    def _err(
        self,
        execution_id: str,
        *,
        code: str,
        msg: str,
        env_fp: str | None = None,
        meta_extra: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        env_fingerprint = env_fp or "adapter=modal"
        return error_envelope(
            execution_id=execution_id,
            code=code,
            message=msg,
            env_fingerprint=env_fingerprint,
            meta_extra=meta_extra,
        )


class CanonicalizationError(RuntimeError):
    pass


class DuplicateTargetError(RuntimeError):
    pass
