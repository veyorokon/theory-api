"""
Local adapter for Docker container execution.

Executes processors as isolated Docker containers with standardized I/O.
"""

import json
import os
import subprocess
import yaml
from pathlib import Path
from typing import Any, Dict, List

from django.conf import settings

from .base import RuntimeAdapter
from .ensure_image import ensure_image
from .envelope import success_envelope, error_envelope, write_outputs_index
from libs.runtime_common.fingerprint import compose_env_fingerprint
from .redaction import redact_msg
from apps.core.utils.processor_ref import registry_path


class LocalAdapter(RuntimeAdapter):
    """Local adapter for Docker container execution."""

    def __init__(self):
        """Initialize local adapter."""
        self.executions = []

    def invoke(
        self,
        *,
        processor_ref: str,
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

        try:
            spec = registry_snapshot["processors"][processor_ref]
            image_digest = spec["image"]["oci"]
            timeout_s = spec.get("runtime", {}).get("timeout_s")
        except Exception as e:
            return error_envelope(
                execution_id=execution_id,
                code=ERR_ADAPTER_INVOCATION,
                message=f"LocalAdapter: bad registry snapshot: {e}",
                env_fingerprint="adapter=local",
            )

        # Call legacy implementation
        legacy_inputs = json.dumps(inputs_json, ensure_ascii=False)
        legacy_opts = json.dumps(adapter_opts, ensure_ascii=False)
        plan_id = execution_id  # Use execution_id as plan_id for legacy

        return self._invoke_legacy(
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

        # Ensure container image is available
        image_ref = ensure_image(registry_spec, adapter="local", build=build_flag)

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

            # Resolve secrets from registry specification
            env_vars = self._resolve_secrets(registry_spec)
            if isinstance(env_vars, dict) and env_vars.get("status") == "error":
                return env_vars  # Return error for missing required secrets

            # Build Docker command
            docker_cmd = self._build_docker_command(
                registry_spec, image_ref, workdir, env_vars, timeout_s, write_prefix, execution_id
            )

            # Execute container
            result = self._execute_container(
                docker_cmd, timeout_s or registry_spec.get("runtime", {}).get("timeout_s", 300)
            )

            # Process outputs
            if result.returncode == 0:
                return self._canonicalize_outputs(
                    outdir=output_dir, write_prefix=write_prefix, registry_spec=registry_spec, execution_id=execution_id
                )
            else:
                return self._process_failure_outputs(result, registry_spec, execution_id)

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

    def _resolve_secrets(self, registry_spec: Dict[str, Any]) -> Dict[str, str]:
        """
        Resolve secrets per registry specification.

        Args:
            registry_spec: Processor specification from registry

        Returns:
            Dict of environment variables or error dict for missing required secrets
        """
        from django.conf import settings

        secrets_spec = registry_spec.get("secrets", {})
        required = secrets_spec.get("required", [])
        optional = secrets_spec.get("optional", [])

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
            f"{workdir}:/work:rw",
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
        cmd.extend(["-e", "THEORY_OUTPUT_DIR=/work/out"])
        cmd.extend(["-e", "ARTIFACTS_BASE_DIR=/artifacts"])

        # Add image and explicit processor command (no ENTRYPOINT in image)
        cmd.append(image_ref)
        cmd.extend(
            [
                "python",
                "/app/main.py",
                "--inputs",
                "/work/inputs.json",
                "--write-prefix",
                write_prefix,
                "--execution-id",
                execution_id,
            ]
        )

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
        self, outdir: Path, write_prefix: str, registry_spec: Dict[str, Any], execution_id: str
    ) -> Dict[str, Any]:
        """Canonicalize outputs with deterministic ordering and index artifact."""
        from apps.storage.artifact_store import artifact_store
        from apps.core.predicates.builtins import canon_path_facet_root
        from apps.core.errors import ERR_OUTPUT_DUPLICATE
        import mimetypes
        import json
        import os

        # Idempotent re-run check as per Twin's spec
        index_path = f"/artifacts/execution/{execution_id}/outputs.json"
        if os.path.exists(index_path):
            try:
                with open(index_path, encoding="utf-8") as f:
                    prev = json.loads(f.read())

                # Compute current outputs (canon_paths → expected outputs)
                files = [p for p in outdir.rglob("*") if p.is_file()]
                expected_outputs = []
                for f in files:
                    rel = f.relative_to(outdir).as_posix()
                    world_path = canon_path_facet_root(f"{write_prefix}{rel}")
                    expected_outputs.append(world_path)

                cur = {"outputs": sorted(expected_outputs)}
                if prev.get("outputs") == cur["outputs"]:
                    # Exact match - return success envelope using existing index
                    image_digest = registry_spec.get("image", {}).get("oci") or "local-build"
                    env_fingerprint = self._build_env_fingerprint(registry_spec)
                    return success_envelope(
                        execution_id=execution_id,
                        outputs=prev["outputs"],
                        index_path=index_path,
                        image_digest=image_digest,
                        env_fingerprint=env_fingerprint,
                        duration_ms=0,
                    )
                else:
                    # Conflict with prior outputs
                    env_fingerprint = self._build_env_fingerprint(registry_spec)
                    return error_envelope(
                        execution_id, ERR_OUTPUT_DUPLICATE, "conflict with prior outputs", env_fingerprint
                    )
            except (json.JSONDecodeError, OSError):
                # Corrupted index file - proceed with normal execution
                pass

        files = [p for p in outdir.rglob("*") if p.is_file()]
        seen = set()
        entries = []
        io_bytes = 0

        for f in files:
            rel = f.relative_to(outdir).as_posix()
            world_path = canon_path_facet_root(f"{write_prefix}{rel}")

            if world_path in seen:
                from apps.core.errors import ERR_OUTPUT_DUPLICATE

                env_fingerprint = self._build_env_fingerprint(registry_spec)
                return error_envelope(
                    execution_id, ERR_OUTPUT_DUPLICATE, f"Duplicate target path: {world_path}", env_fingerprint
                )
            seen.add(world_path)

            data = f.read_bytes()
            cid = artifact_store.compute_cid(data)
            size = len(data)
            io_bytes += size

            mime = mimetypes.guess_type(world_path)[0] or "application/octet-stream"
            stored = artifact_store.put_bytes(world_path, data, mime)

            entries.append({"path": stored, "cid": cid, "size_bytes": size, "mime": mime})

        # Create index artifact with centralized helper
        index_path = f"/artifacts/execution/{execution_id}/outputs.json"
        index_bytes = write_outputs_index(index_path, entries)
        artifact_store.put_bytes(index_path, index_bytes, "application/json")

        # Use shared envelope serializer
        image_digest = registry_spec.get("image", {}).get("oci") or "local-build"
        env_fingerprint = self._build_env_fingerprint(registry_spec)
        meta_extra = {"io_bytes": io_bytes}

        return success_envelope(execution_id, entries, index_path, image_digest, env_fingerprint, 0, meta_extra)

    def _process_failure_outputs(
        self, result: subprocess.CompletedProcess, registry_spec: Dict[str, Any], execution_id: str
    ) -> Dict[str, Any]:
        """Process failed container execution."""
        error_msg = f"Container failed with exit code {result.returncode}"
        if result.stderr.strip():
            # Redact sensitive information from stderr
            stderr_tail = redact_msg(result.stderr[:200])
            error_msg += f". STDERR: {stderr_tail}"
        if result.stdout.strip():
            # Redact sensitive information from stdout
            stdout_tail = redact_msg(result.stdout[:200])
            error_msg += f". STDOUT: {stdout_tail}"

        env_fingerprint = self._build_env_fingerprint(registry_spec)
        return error_envelope(execution_id, "container_execution_failed", error_msg, env_fingerprint)

    def _build_env_fingerprint(self, registry_spec: Dict[str, Any]) -> str:
        """Build environment fingerprint using shared function."""
        image = registry_spec.get("image", {})
        runtime = registry_spec.get("runtime", {})
        secrets = registry_spec.get("secrets", {})

        # Build key-value pairs for fingerprint
        kv = {}

        # Add image if present
        if "oci" in image:
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
