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

from apps.core.orchestrator import run_processor_core
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
            choices=["default", "smoke"],
            default="default",
            help="Execution mode: 'default' (normal), 'smoke' (hermetic, no external services)",
        )
        parser.add_argument("--plan", help="Plan key for budget tracking (creates if not exists)")
        parser.add_argument(
            "--write-prefix", default="/artifacts/outputs/", help="Write prefix for outputs (must end with /)"
        )
        parser.add_argument("--inputs-json", default="{}", help="JSON input for processor")
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
        parser.add_argument("--global-receipt-base", default="/artifacts", help="Base path for global receipts")

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

        # Require {execution_id} in write prefix for collision prevention
        write_prefix = options["write_prefix"]
        if "{execution_id}" not in write_prefix:
            from django.core.management.base import CommandError

            raise CommandError("--write-prefix must include '{execution_id}' to prevent output collisions")

        # Parse inputs
        try:
            inputs_json = json.loads(options["inputs_json"])
        except json.JSONDecodeError as e:
            self.stderr.write(f"Error: Invalid --inputs-json: {e}")
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

        # Set global receipt base in environment for processors
        import os

        os.environ["GLOBAL_RECEIPT_BASE"] = options["global_receipt_base"]

        # Call core function
        result = run_processor_core(
            ref=options["ref"],
            adapter=options["adapter"],
            mode=options["mode"],
            inputs_json=inputs_json,
            write_prefix=options["write_prefix"],
            plan=options.get("plan"),
            adapter_opts=adapter_opts,
            build=options.get("build", False),
            timeout=options.get("timeout"),
        )

        # Download outputs if requested
        if result.get("status") == "success" and result.get("outputs"):
            if options.get("save_dir"):
                self._download_all_outputs(result["outputs"], options["save_dir"], options)
            elif options.get("save_first"):
                self._download_first_output(result["outputs"], options["save_first"], options)

        # Always output JSON (for both success and error)
        self.stdout.write(json.dumps(result, ensure_ascii=False, separators=(",", ":")))

        # Return None to satisfy Django management command contract
        return None
