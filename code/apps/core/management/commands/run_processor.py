"""
Run processor management command - CLI wrapper around core processor execution.

Pure function available at libs.runtime_common.core.run_processor_core for programmatic use.
"""

from __future__ import annotations
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from django.core.management.base import BaseCommand
from libs.runtime_common.envelope import resolve_mode, ModeSafetyError

# WebSocket orchestrator now used for all processors
from libs.runtime_common import logging as core_logging
from libs.runtime_common.logging import bind, clear
from apps.storage.artifact_store import artifact_store


class Command(BaseCommand):
    """Run processor CLI - prints JSON envelope to stdout."""

    help = "Run processor with adapter selection and return JSON envelope"

    def add_arguments(self, parser):
        """Add command-line arguments."""
        parser.add_argument("--ref", required=True, help="Processor reference (e.g., llm/litellm@1)")
        parser.add_argument("--adapter", choices=["local", "modal"], default="local", help="Execution adapter to use")
        parser.add_argument(
            "--mode",
            choices=["real", "mock"],
            help="Processor mode",
        )
        parser.add_argument("--plan", help="Plan key for budget tracking (creates if not exists)")
        parser.add_argument(
            "--write-prefix",
            default="/artifacts/outputs/{execution_id}/",
            help="Write prefix for outputs (must include {execution_id})",
        )
        # JSON input options (mutually exclusive)
        inputs_group = parser.add_mutually_exclusive_group()
        inputs_group.add_argument("--inputs-jsonstr", default="{}", help="JSON input as string (legacy)")
        inputs_group.add_argument("--inputs-json", help="JSON input (no escaping required)")
        inputs_group.add_argument("--inputs-file", help="Read JSON input from file")
        inputs_group.add_argument("--inputs", help="Read JSON from stdin (use '-')")
        parser.add_argument("--adapter-opts-json", help="Optional adapter-specific options as JSON")
        parser.add_argument("--attach", action="append", help="Attach file as name=path (can be used multiple times)")
        parser.add_argument("--json", action="store_true", help="Output JSON response")
        parser.add_argument("--timeout", type=int, help="Timeout in seconds")
        parser.add_argument(
            "--build",
            action="store_true",
            help="Build container image if not available (requires build spec in registry)",
        )
        parser.add_argument("--save-dir", help="Download all outputs into this directory (mirrors world paths)")
        parser.add_argument("--save-first", help="Download only the first output into this file path")

    def materialize_attachments(self, attachments: List[str]) -> Dict[str, Dict[str, Any]]:
        """Materialize attachment files and return mapping."""
        if not attachments:
            return {}

        attachment_map = {}

        for attach_spec in attachments:
            if "=" not in attach_spec:
                self.stderr.write(f"Invalid attachment format: {attach_spec} (expected name=path)")
                continue

            name, path = attach_spec.split("=", 1)
            file_path = Path(path)

            if not file_path.exists():
                self.stderr.write(f"Attachment file not found: {path}")
                continue

            # Read file data
            with open(file_path, "rb") as f:
                data = f.read()

            # Compute CID
            cid = artifact_store.compute_cid(data)

            # Determine MIME type
            import mimetypes

            mime_type, _ = mimetypes.guess_type(str(file_path))
            if not mime_type:
                mime_type = "application/octet-stream"

            # Store in artifact store
            artifact_path = f"/artifacts/inputs/{cid}/{file_path.name}"
            artifact_store.put_bytes(artifact_path, data, mime_type)

            attachment_map[name] = {"$artifact": artifact_path, "cid": cid, "mime": mime_type}

            # Note: will check json flag in caller context

        return attachment_map

    def parse_inputs(self, options: Dict[str, Any]) -> Dict[str, Any]:
        """Parse JSON inputs from various sources with priority handling."""
        inputs_jsonstr = options.get("inputs_jsonstr", "{}")
        inputs_json = options.get("inputs_json")
        inputs_file = options.get("inputs_file")
        inputs_stdin = options.get("inputs")

        # Determine input source by priority: stdin > file > json > jsonstr
        try:
            if inputs_stdin == "-":
                # Read from stdin
                json_text = sys.stdin.read()
                if not json_text.strip():
                    return json.loads("{}")
                return json.loads(json_text)
            elif inputs_file:
                # Read from file
                with open(inputs_file, encoding="utf-8") as f:
                    return json.load(f)
            elif inputs_json:
                # Parse direct JSON (no string escaping)
                return json.loads(inputs_json)
            else:
                # Legacy string parsing (with deprecation warning)
                if inputs_jsonstr != "{}":
                    import warnings

                    warnings.warn(
                        "--inputs-jsonstr is deprecated, use --inputs-json for cleaner syntax",
                        DeprecationWarning,
                        stacklevel=2,
                    )
                return json.loads(inputs_jsonstr)
        except json.JSONDecodeError as e:
            # Provide context-specific error messages
            if inputs_stdin == "-":
                source = "stdin"
            elif inputs_file:
                source = f"file '{inputs_file}'"
            elif inputs_json:
                source = "--inputs-json"
            else:
                source = "--inputs-jsonstr"

            self.stderr.write(f"Error: Invalid JSON in {source}: {e}")
            sys.exit(1)
        except FileNotFoundError as e:
            self.stderr.write(f"Error: Input file not found: {inputs_file}")
            sys.exit(1)

    def rewrite_attach_references(self, obj: Any, attachment_map: Dict[str, Dict[str, Any]]) -> Any:
        """Recursively rewrite $attach references to $artifact."""
        if isinstance(obj, dict):
            if "$attach" in obj and len(obj) == 1:
                attach_name = obj["$attach"]
                if attach_name in attachment_map:
                    return attachment_map[attach_name]
                else:
                    self.stderr.write(f"Warning: attachment '{attach_name}' not found")
                    return obj
            return {k: self.rewrite_attach_references(v, attachment_map) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self.rewrite_attach_references(item, attachment_map) for item in obj]
        return obj

    def _download_all_outputs(self, outputs: List[Dict[str, Any]], save_dir: str, options: Dict[str, Any]) -> None:
        """Download all outputs to save_dir, mirroring world paths."""
        save_path = Path(save_dir)
        save_path.mkdir(parents=True, exist_ok=True)

        for output in outputs:
            if not isinstance(output, dict) or "path" not in output:
                continue

            world_path = output["path"]
            # Create relative path from world path (strip leading /)
            rel_path = world_path.lstrip("/")
            local_path = save_path / rel_path

            # Create parent directories
            local_path.parent.mkdir(parents=True, exist_ok=True)

            # Download from artifact store
            try:
                content = artifact_store.get_bytes(world_path)
                with open(local_path, "wb") as f:
                    f.write(content)
                if not options.get("json"):
                    self.stdout.write(f"Downloaded {world_path} -> {local_path}")
            except Exception as e:
                self.stderr.write(f"Failed to download {world_path}: {e}")

    def _download_first_output(self, outputs: List[Dict[str, Any]], save_path: str, options: Dict[str, Any]) -> None:
        """Download only the first output to save_path."""
        if not outputs or not isinstance(outputs[0], dict) or "path" not in outputs[0]:
            return

        output = outputs[0]
        world_path = output["path"]
        local_path = Path(save_path)

        # Create parent directories
        local_path.parent.mkdir(parents=True, exist_ok=True)

        # Download from artifact store
        try:
            content = artifact_store.get_bytes(world_path)
            with open(local_path, "wb") as f:
                f.write(content)
            if not options.get("json"):
                self.stdout.write(f"Downloaded first output {world_path} -> {local_path}")
        except Exception as e:
            self.stderr.write(f"Failed to download {world_path}: {e}")

    def handle(self, *args, **options):
        """Execute the command - calls core function and prints JSON to stdout."""
        import uuid

        if options.get("json"):
            import os

            os.environ["LOG_STREAM"] = "stderr"

        # Generate execution_id early for consistent logging context
        execution_id = str(uuid.uuid4())

        # Bind logging context with real execution_id before core function call
        bind(
            trace_id=execution_id,
            processor_ref=options["ref"],
            adapter=options["adapter"],
            mode=options.get("mode", "mock"),
        )

        try:
            # Require {execution_id} in write prefix for collision prevention
            write_prefix = options["write_prefix"]
            if "{execution_id}" not in write_prefix:
                from django.core.management.base import CommandError

                raise CommandError("--write-prefix must include '{execution_id}' to prevent output collisions")

            # Parse inputs using new helper
            inputs_json = self.parse_inputs(options)

            # Inject mode into inputs if specified
            if options.get("mode"):
                inputs_json["mode"] = options["mode"]
            else:
                import os

                if os.environ.get("CI") == "true" and "mode" not in inputs_json:
                    # CI ergonomic default: set mode to mock if not specified
                    inputs_json["mode"] = "mock"

            # CI guardrail: validate mode before proceeding
            try:
                resolve_mode(options.get("mode"))  # This will raise if CI=true and mode=real
            except ModeSafetyError as e:
                # Explicit non-zero exit for guardrail violation; no adapter invoked
                # Note: No execution_id available yet for early failures
                core_logging.error(
                    "execution.fail",
                    error={"code": "ERR_CI_SAFETY", "message": e.message},
                    reason="ci_guardrail_block",
                    ci=True,
                    mode="real",
                )
                self.stderr.write(f"Error: {e.message}")
                sys.exit(1)
            except Exception as e:
                # Keep existing behavior for other validation errors
                # Note: No execution_id available yet for early failures
                core_logging.error("execution.fail", error={"code": "ERR_MODE_INVALID", "message": str(e)})
                self.stderr.write(f"Error: {e}")
                sys.exit(1)

            # Materialize attachments
            attachment_map = {}
            if options.get("attach"):
                attachment_map = self.materialize_attachments(options["attach"])
                if not options.get("json"):
                    for name, info in attachment_map.items():
                        self.stdout.write(f"Materialized {name} -> {info.get('$artifact')} ({info.get('cid')})")

            # Rewrite $attach references in inputs
            if attachment_map:
                inputs_json = self.rewrite_attach_references(inputs_json, attachment_map)

            # Parse adapter options
            adapter_opts = json.loads(options.get("adapter_opts_json") or "{}")

            # Extract Modal context from Django settings
            from django.conf import settings

            # Use WebSocket orchestrator (standardized)
            from apps.core.orchestrator_ws import OrchestratorWS

            orch = OrchestratorWS()

            result = orch.invoke(
                ref=options["ref"],
                mode=options["mode"],
                inputs=inputs_json,
                build=options.get("build", False),
                stream=False,  # For CLI, we want final result only
                timeout_s=options.get("timeout", 600),
                execution_id=execution_id,
                write_prefix=options["write_prefix"],
                adapter=options["adapter"],  # Pass adapter selection to orchestrator
            )

            # Download outputs if requested
            if result.get("status") == "success" and result.get("outputs"):
                if options.get("save_dir"):
                    self._download_all_outputs(result["outputs"], options["save_dir"], options)
                elif options.get("save_first"):
                    self._download_first_output(result["outputs"], options["save_first"], options)

            # Always output JSON (for both success and error)
            self.stdout.write(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")

            # Return None to satisfy Django management command contract
            return None

        finally:
            # Clear logging context to prevent leakage
            clear()
