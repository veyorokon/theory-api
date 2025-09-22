"""
Local adapter for Docker container execution.

Executes processors as isolated Docker containers with standardized I/O.
"""

import json
import logging
import os
import re
import subprocess
import yaml
from pathlib import Path
from typing import Any, Dict, List

from django.conf import settings

from .base import RuntimeAdapter
from .ensure_image import ensure_image
from libs.runtime_common.envelope import success_envelope, error_envelope, write_outputs_index
from libs.runtime_common.fingerprint import compose_env_fingerprint
from libs.runtime_common.redaction import redact_msg
from apps.core.utils.processor_ref import registry_path, local_processor_path
from apps.core.logging import bind, clear, info, error

logger = logging.getLogger(__name__)


def _world_to_host_artifacts(host_artifacts: Path, world_path: str) -> Path:
    """Map world path (/artifacts/...) to host filesystem path."""
    if not world_path.startswith("/artifacts/"):
        raise ValueError(f"expected /artifacts/* path, got: {world_path}")
    rel = world_path[len("/artifacts/") :]
    return host_artifacts / rel


def _extract_paths_from_outputs(outputs: List) -> List[str]:
    """Extract path strings from output objects or return strings directly."""
    paths = []
    for output in outputs:
        if isinstance(output, dict) and "path" in output:
            paths.append(output["path"])
        elif isinstance(output, str):
            paths.append(output)
    return paths


class LocalAdapter(RuntimeAdapter):
    """Local adapter for Docker container execution."""

    def __init__(self):
        """Initialize local adapter."""
        self.executions = []

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
        """
        Invoke processor using new keyword-only signature.
        """
        return self.invoke_kw(
            processor_ref=processor_ref,
            mode=mode,
            inputs_json=inputs_json,
            write_prefix=write_prefix,
            execution_id=execution_id,
            registry_snapshot=registry_snapshot,
            adapter_opts=adapter_opts,
            secrets_present=secrets_present,
        )

    def invoke_kw(
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
        """
        Keyword-only invoke that adapts to legacy implementation.
        """
        from .envelope import error_envelope
        from apps.core.errors import ERR_ADAPTER_INVOCATION

        # Bind adapter context and log invoke
        bind(trace_id=execution_id, adapter="local", processor_ref=processor_ref, mode=mode)

        try:
            spec = registry_snapshot["processors"][processor_ref]
            image_digest = spec["image"]["oci"]
            timeout_s = spec.get("runtime", {}).get("timeout_s")

            info(
                "adapter.invoke",
                image_digest=image_digest,
                build=adapter_opts.get("build", False),
                write_prefix=write_prefix,
            )
        except Exception as e:
            error(
                "adapter.complete",
                status="error",
                error={"code": ERR_ADAPTER_INVOCATION, "message": f"LocalAdapter: bad registry snapshot: {e}"},
            )
            return error_envelope(
                execution_id=execution_id,
                code=ERR_ADAPTER_INVOCATION,
                message=f"LocalAdapter: bad registry snapshot: {e}",
                env_fingerprint="adapter=local",
            )

        try:
            # Call legacy implementation
            legacy_inputs = json.dumps(inputs_json, ensure_ascii=False)
            legacy_opts = json.dumps(adapter_opts, ensure_ascii=False)
            plan_id = execution_id  # Use execution_id as plan_id for legacy

            result = self._invoke_legacy(
                processor_ref,
                image_digest,
                legacy_inputs,
                write_prefix,
                plan_id,
                execution_id=execution_id,
                timeout_s=timeout_s,
                secrets=secrets_present,
                adapter_opts_json=legacy_opts,
                build=adapter_opts.get("build", False),
            )

            # Log completion with boundary discipline
            if result.get("status") == "success":
                outputs = result.get("outputs", [])
                info("adapter.complete", status="success", outputs_count=len(outputs))
            else:
                error("adapter.complete", status="error", error=result.get("error", {}))

            return result

        except Exception as e:
            error("adapter.complete", status="error", error={"code": ERR_ADAPTER_INVOCATION, "message": str(e)})
            raise
        finally:
            clear()

    def _invoke_legacy(
        self,
        processor_ref: str,
        image_digest: str,  # Not used - we read from registry
        inputs_json: str,
        write_prefix: str,
        plan_id: str,
        execution_id: str,
        timeout_s: int | None = None,
        secrets: List[str] | None = None,
        adapter_opts_json: str | None = None,
        build: bool = False,
    ) -> Dict[str, Any]:
        """
        Invoke processor in Docker container.

        Args:
            processor_ref: Processor reference (e.g., 'llm/litellm@1')
            image_digest: Ignored - read from registry
            inputs_json: JSON string with processor inputs
            write_prefix: Prefix path for outputs
            plan_id: Plan identifier
            timeout_s: Optional timeout in seconds
            secrets: Optional list of secret names
            adapter_opts_json: Optional adapter-specific options
            build: Whether to build image if not available

        Returns:
            Execution result from container execution
        """
        # Validate write prefix
        if not self.validate_write_prefix(write_prefix):
            raise ValueError(f"Invalid write_prefix: {write_prefix}")

        # Load processor registry specification
        registry_spec = self._load_registry_spec(processor_ref)

        # Parse adapter options
        adapter_opts = {}
        if adapter_opts_json:
            try:
                adapter_opts = json.loads(adapter_opts_json)
            except json.JSONDecodeError:
                pass

        # Extract build flag from adapter options
        build_flag = adapter_opts.get("build", build)

        # -----------------------------
        # Optional local build (immutable run by image ID)
        # -----------------------------
        image_ref = ensure_image(registry_spec, adapter="local", build=False)  # default: pinned digest
        image_to_run = image_ref  # default: pinned digest
        image_tag_for_logs = None  # human-friendly, optional
        image_id_for_meta = image_ref  # default to pinned digest; overwritten if build=True

        if build_flag:
            slug = re.sub(r"[^a-z0-9\-]+", "-", processor_ref.lower().replace("/", "-").replace("@", "-v"))
            short = os.getenv("GITHUB_SHA", "")[:7] or "dev"
            local_tag = f"theory-local/{slug}:{short}"

            processor_dir = local_processor_path(processor_ref)
            dockerfile_path = processor_dir / "Dockerfile"
            # Build context must be project root for Dockerfile paths to work
            from django.conf import settings

            build_ctx = Path(settings.BASE_DIR)

            if not dockerfile_path.exists():
                raise RuntimeError(f"Dockerfile missing for {processor_ref}: {dockerfile_path}")

            # build multi-arch isn't needed for local; ensure --load to get a local image
            subprocess.check_call(
                [
                    "docker",
                    "buildx",
                    "build",
                    "--load",
                    "-t",
                    local_tag,
                    "--label",
                    f"org.opencontainers.image.revision={short}",
                    "-f",
                    str(dockerfile_path),
                    str(build_ctx),
                ]
            )
            # capture immutable image ID (sha256:...)
            image_id = subprocess.check_output(
                ["docker", "inspect", "--format", "{{.Id}}", local_tag], text=True
            ).strip()

            image_to_run = image_id  # run by immutable ID
            image_id_for_meta = image_id  # record in receipts/meta
            image_tag_for_logs = local_tag  # optional, for humans/logs

        # Use orchestrator-provided execution_id (never generate/override)
        workdir = self._create_workdir(plan_id, plan_id)

        try:
            # Write inputs.json to workdir
            inputs_file = workdir / "inputs.json"
            with open(inputs_file, "w") as f:
                f.write(inputs_json)

            # Create output directory
            output_dir = workdir / "out"
            output_dir.mkdir(exist_ok=True)

            # Resolve secrets from registry specification (only required in real mode)
            try:
                inputs = json.loads(inputs_json)
                mode = inputs.get("mode", "mock")
            except (json.JSONDecodeError, AttributeError):
                mode = "mock"  # Default to mock if parsing fails

            env_vars = self._resolve_secrets(registry_spec, mode)
            if isinstance(env_vars, dict) and env_vars.get("status") == "error":
                return env_vars  # Return error for missing required secrets

            # Build Docker command
            docker_cmd = self._build_docker_command(
                registry_spec, image_to_run, workdir, env_vars, timeout_s, write_prefix, execution_id
            )

            # Execute container
            result = self._execute_container(
                docker_cmd, timeout_s or registry_spec.get("runtime", {}).get("timeout_s", 300)
            )

            # Process outputs
            if result.returncode == 0:
                # Get host_artifacts for path mapping
                host_artifacts = os.environ.get("ARTIFACTS_HOST_DIR", os.path.abspath("./artifacts"))
                return self._canonicalize_outputs(
                    write_prefix=write_prefix,
                    registry_spec=registry_spec,
                    execution_id=execution_id,
                    image_ref=image_to_run,
                    image_id_for_meta=image_id_for_meta,
                    image_tag_for_logs=image_tag_for_logs,
                    host_artifacts=host_artifacts,
                )
            else:
                return self._process_failure_outputs(
                    result, registry_spec, execution_id, image_ref=image_to_run, image_id_for_meta=image_id_for_meta
                )

        finally:
            # Clean up workdir
            self._cleanup_workdir(workdir)

    def _load_registry_spec(self, processor_ref: str) -> Dict[str, Any]:
        """Load processor specification from registry YAML."""
        registry_file = registry_path(processor_ref)

        if not registry_file.exists():
            raise FileNotFoundError(f"Registry file not found: {registry_file}")

        with open(registry_file) as f:
            return yaml.safe_load(f)

    def _resolve_secrets(self, registry_spec: Dict[str, Any], mode: str = "mock") -> Dict[str, str]:
        """
        Resolve secrets per registry specification.

        Args:
            registry_spec: Processor specification from registry
            mode: Processor mode ("mock" or "real") - secrets only required in real mode

        Returns:
            Dict of environment variables or error dict for missing required secrets
        """
        from django.conf import settings

        secrets_spec = registry_spec.get("secrets", {})
        required = secrets_spec.get("required", [])
        optional = secrets_spec.get("optional", [])

        # In mock mode, skip secret validation for hermetic PR lane testing
        if mode == "mock":
            return {}  # Return empty env vars for mock mode

        env_vars = {}
        missing_required = []

        for secret_name in required + optional:
            # Try os.environ first, then settings fallback
            value = os.environ.get(secret_name)
            if value is None:
                value = getattr(settings, secret_name, None)

            if value is not None:
                env_vars[secret_name] = value
            elif secret_name in required:
                missing_required.append(secret_name)

        if missing_required:
            return {"status": "error", "error": f"Missing required secrets: {missing_required}"}

        return env_vars

    def _create_workdir(self, plan_id: str, execution_id: str) -> Path:
        """Create temporary workdir for container execution."""
        workdir = Path(settings.BASE_DIR) / "tmp" / plan_id / str(execution_id)
        workdir.mkdir(parents=True, exist_ok=True)
        return workdir

    def _cleanup_workdir(self, workdir: Path) -> None:
        """Clean up temporary workdir."""
        import shutil

        if workdir.exists():
            shutil.rmtree(workdir)

    def _build_docker_command(
        self,
        registry_spec: Dict[str, Any],
        image_ref: str,
        workdir: Path,
        env_vars: Dict[str, str],
        timeout_s: int | None,
        write_prefix: str,
        execution_id: str,
    ) -> List[str]:
        """Build Docker run command from registry specification."""
        runtime = registry_spec.get("runtime", {})
        entrypoint = registry_spec.get("entrypoint", {})

        # Ensure artifacts directory exists and is mounted
        host_artifacts = os.environ.get("ARTIFACTS_HOST_DIR", os.path.abspath("./artifacts"))
        os.makedirs(host_artifacts, exist_ok=True)

        cmd = [
            "docker",
            "run",
            "--rm",
            "--workdir",
            "/work",
            "-v",
            f"{workdir}:/tmp/execution:rw",
            "-v",
            f"{host_artifacts}:/artifacts:rw",
        ]

        # Add resource constraints
        if "cpu" in runtime:
            cmd.extend(["--cpus", str(runtime["cpu"])])
        if "memory_gb" in runtime:
            cmd.extend(["--memory", f"{runtime['memory_gb']}g"])

        # Add environment variables
        for key, value in env_vars.items():
            cmd.extend(["-e", f"{key}={value}"])

        # Add standard environment variables
        cmd.extend(["-e", "THEORY_OUTPUT_DIR=/tmp/execution/out"])
        cmd.extend(["-e", "ARTIFACTS_BASE_DIR=/artifacts"])
        cmd.extend(["-e", f"IMAGE_REF={image_ref}"])

        # Add image and processor arguments (uses container's ENTRYPOINT)
        cmd.append(image_ref)
        cmd.extend(
            [
                "--inputs",
                "/tmp/execution/inputs.json",
                "--write-prefix",
                write_prefix,
                "--execution-id",
                execution_id,
            ]
        )

        logger.debug("Built Docker command: %s", " ".join(cmd))
        return cmd

    def _execute_container(self, docker_cmd: List[str], timeout_s: int) -> subprocess.CompletedProcess:
        """Execute Docker container with timeout."""
        try:
            return subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                check=False,  # Don't raise on non-zero exit
            )
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess(docker_cmd, 124, "", f"Container execution timed out after {timeout_s}s")

    def _canonicalize_outputs(
        self,
        write_prefix: str,
        registry_spec: Dict[str, Any],
        execution_id: str,
        image_ref: str,
        image_id_for_meta: str,
        image_tag_for_logs: str = None,
        host_artifacts: str = None,
    ) -> Dict[str, Any]:
        """Canonicalize outputs with deterministic ordering and index artifact."""
        from apps.storage.artifact_store import artifact_store
        from apps.core.predicates.builtins import canon_path_facet_root
        from apps.core.errors import ERR_OUTPUT_DUPLICATE
        import mimetypes
        import json
        import os

        # Use host_artifacts path mapping instead of scanning unused outdir
        if host_artifacts is None:
            host_artifacts = os.environ.get("ARTIFACTS_HOST_DIR", os.path.abspath("./artifacts"))

        host_artifacts_path = Path(host_artifacts)

        # Expand {execution_id} in write_prefix before any path operations
        expanded_write_prefix = write_prefix.format(execution_id=execution_id)

        # Get world paths for files to process
        paths: List[str] = []

        # Primary: Check for processor-written global index
        host_index_global = _world_to_host_artifacts(
            host_artifacts_path, f"/artifacts/execution/{execution_id}/outputs.json"
        )

        # Secondary: Check for local index in expanded write_prefix
        host_index_local = _world_to_host_artifacts(host_artifacts_path, expanded_write_prefix) / "outputs.json"

        if host_index_global.exists():
            # Use processor-authored list (source of truth)
            try:
                data = json.loads(host_index_global.read_text(encoding="utf-8"))
                paths = _extract_paths_from_outputs(data.get("outputs", []))
                logger.debug(f"Using processor global index with {len(paths)} outputs")
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to read global index {host_index_global}: {e}")
                paths = []
        elif host_index_local.exists():
            # Use local index as fallback
            try:
                data = json.loads(host_index_local.read_text(encoding="utf-8"))
                paths = _extract_paths_from_outputs(data.get("outputs", []))
                logger.debug(f"Using processor local index with {len(paths)} outputs")
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to read local index {host_index_local}: {e}")
                paths = []

        if not paths:
            # Fallback: enumerate under the host prefix deterministically (use expanded prefix)
            host_prefix = _world_to_host_artifacts(host_artifacts_path, expanded_write_prefix)
            outputs_dir = host_prefix / "outputs"

            if outputs_dir.exists():
                files = [p for p in outputs_dir.rglob("*") if p.is_file()]
                # Convert each host file path back to world paths
                paths = [f"/artifacts/{p.relative_to(host_artifacts_path).as_posix()}" for p in sorted(files)]
                logger.debug(f"Fallback scan found {len(paths)} outputs")
            else:
                logger.debug(f"No outputs directory found at {outputs_dir}")
                paths = []

        # Idempotent re-run check
        # Use write_prefix for index_path instead of execution artifacts path
        expanded_write_prefix = write_prefix.format(execution_id=execution_id)
        index_path = f"{expanded_write_prefix.rstrip('/')}/outputs.json"
        if host_index_global.exists():
            try:
                prev_data = json.loads(host_index_global.read_text(encoding="utf-8"))
                prev_outputs = prev_data.get("outputs", [])

                if sorted(prev_outputs) == sorted(paths):
                    # Exact match - return success envelope using existing index
                    image_digest = (
                        image_ref if image_ref else registry_spec.get("image", {}).get("oci") or "local-build"
                    )
                    env_fingerprint = self._build_env_fingerprint(registry_spec, image_ref)
                    return success_envelope(
                        execution_id=execution_id,
                        outputs=prev_outputs,
                        index_path=index_path,
                        image_digest=image_digest,
                        env_fingerprint=env_fingerprint,
                        duration_ms=0,
                    )
            except (json.JSONDecodeError, OSError):
                # Corrupted index file - proceed with normal execution
                pass
        seen = set()
        entries = []
        io_bytes = 0

        for world_path in paths:
            # Map world path to host filesystem path
            host_path = _world_to_host_artifacts(host_artifacts_path, world_path)

            if not host_path.exists():
                logger.warning(f"Expected file not found: {host_path} (world: {world_path})")
                continue

            if world_path in seen:
                from apps.core.errors import ERR_OUTPUT_DUPLICATE

                env_fingerprint = self._build_env_fingerprint(registry_spec, image_ref)
                return error_envelope(
                    execution_id, ERR_OUTPUT_DUPLICATE, f"Duplicate target path: {world_path}", env_fingerprint
                )
            seen.add(world_path)

            data = host_path.read_bytes()
            cid = artifact_store.compute_cid(data)
            size = len(data)
            io_bytes += size

            mime = mimetypes.guess_type(world_path)[0] or "application/octet-stream"
            stored = artifact_store.put_bytes(world_path, data, mime)

            entries.append({"path": stored, "cid": cid, "size_bytes": size, "mime": mime})

        # Create index artifact with centralized helper
        # Use write_prefix for index_path (where outputs actually live)
        expanded_write_prefix = write_prefix.format(execution_id=execution_id)
        index_path = f"{expanded_write_prefix.rstrip('/')}/outputs.json"
        index_bytes = write_outputs_index(index_path, entries)
        artifact_store.put_bytes(index_path, index_bytes, "application/json")

        # Use shared envelope serializer
        # env fingerprint should include the immutable identifier we actually ran
        env_fingerprint = self._build_env_fingerprint(registry_spec, image_id_for_meta)

        meta = {"env_fingerprint": env_fingerprint}
        # record the actual image we ran
        meta["image_digest"] = image_id_for_meta
        if image_tag_for_logs:
            meta["image_tag"] = image_tag_for_logs
        # existing code may add duration_ms, io_bytes, etc.
        meta["io_bytes"] = io_bytes

        return success_envelope(execution_id, entries, index_path, image_id_for_meta, env_fingerprint, 0, meta)

    def _process_failure_outputs(
        self,
        result: subprocess.CompletedProcess,
        registry_spec: Dict[str, Any],
        execution_id: str,
        image_ref: str,
        image_id_for_meta: str = None,
    ) -> Dict[str, Any]:
        """Process failed container execution."""
        error_msg = f"Container failed with exit code {result.returncode}"
        if result.stderr.strip():
            # Redact sensitive information from stderr (keep full traceback for debugging)
            stderr_full = redact_msg(result.stderr[:8192])  # Increased from 200 to 8KB
            error_msg += f". STDERR:\n{stderr_full}"
        if result.stdout.strip():
            # Redact sensitive information from stdout
            stdout_tail = redact_msg(result.stdout[:200])
            error_msg += f". STDOUT: {stdout_tail}"

        # Use image metadata for proper fingerprinting
        image_digest = image_id_for_meta or image_ref
        env_fingerprint = self._build_env_fingerprint(registry_spec, image_digest)
        return error_envelope(execution_id, "container_execution_failed", error_msg, env_fingerprint)

    def _build_env_fingerprint(self, registry_spec: Dict[str, Any], image_ref: str = None) -> str:
        """Build environment fingerprint using shared function."""
        image = registry_spec.get("image", {})
        runtime = registry_spec.get("runtime", {})
        secrets = registry_spec.get("secrets", {})

        # Build key-value pairs for fingerprint
        kv = {}

        # Add image - use actual image_ref if provided, otherwise fallback to registry OCI
        if image_ref:
            kv["image"] = image_ref
        elif "oci" in image:
            kv["image"] = image["oci"]

        # Add runtime specs
        if "cpu" in runtime:
            kv["cpu"] = str(runtime["cpu"])
        if "memory_gb" in runtime:
            kv["memory"] = f"{runtime['memory_gb']}gb"

        # Add sorted secret names (not values)
        secret_names = secrets.get("required", []) + secrets.get("optional", [])
        if secret_names:
            kv["secrets"] = ",".join(sorted(secret_names))

        # Use shared function to compose fingerprint
        return compose_env_fingerprint(**kv) if kv else "local-docker"
