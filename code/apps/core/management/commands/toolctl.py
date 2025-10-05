"""Tool catalog operations (sync, enable, disable)."""

from __future__ import annotations

import sys

from django.core.management.base import BaseCommand, CommandError

from apps.core.registry.loader import list_processor_refs, load_processor_spec
from apps.tools.models import Tool


class Command(BaseCommand):
    help = "Tool catalog operations: sync, enable, disable"

    def add_arguments(self, parser):
        sub = parser.add_subparsers(dest="subcmd", required=True)

        # sync - sync from registry.yaml to DB
        p_sync = sub.add_parser("sync", help="Sync tools from registry.yaml files to database")
        p_sync.add_argument("--dry-run", action="store_true", help="Show what would be synced")
        p_sync.add_argument("--all", action="store_true", help="Sync all tools (ignore enabled field)")
        p_sync.add_argument("--json", action="store_true", help="Output JSON")

        # enable - enable a tool by ref
        p_enable = sub.add_parser("enable", help="Enable a tool")
        p_enable.add_argument("--ref", required=True, help="Tool ref (e.g., llm/litellm@1)")
        p_enable.add_argument("--json", action="store_true", help="Output JSON")

        # disable - disable a tool by ref
        p_disable = sub.add_parser("disable", help="Disable a tool")
        p_disable.add_argument("--ref", required=True, help="Tool ref (e.g., llm/litellm@1)")
        p_disable.add_argument("--json", action="store_true", help="Output JSON")

        # list - list all tools
        p_list = sub.add_parser("list", help="List all tools in database")
        p_list.add_argument("--enabled-only", action="store_true", help="Show only enabled tools")
        p_list.add_argument("--json", action="store_true", help="Output JSON")

    def handle(self, *args, **opts):
        subcmd = opts["subcmd"]

        if subcmd == "sync":
            self.handle_sync(opts)
        elif subcmd == "enable":
            self.handle_enable(opts)
        elif subcmd == "disable":
            self.handle_disable(opts)
        elif subcmd == "list":
            self.handle_list(opts)

    def handle_sync(self, opts):
        """Sync tools from registry.yaml to database."""
        dry_run = opts["dry_run"]
        sync_all = opts["all"]
        json_mode = opts["json"]

        refs = list_processor_refs()
        created = 0
        updated = 0
        skipped = 0
        errors = []

        for ref in refs:
            try:
                spec = load_processor_spec(ref)
            except Exception as e:
                errors.append({"ref": ref, "error": str(e)})
                if not json_mode:
                    self.stdout.write(self.style.WARNING(f"Failed to load {ref}: {e}"))
                continue

            # Parse ref
            try:
                ns, rest = ref.split("/", 1)
                name, ver = rest.split("@", 1)
                version = int(ver)
            except ValueError:
                errors.append({"ref": ref, "error": "Invalid ref format"})
                if not json_mode:
                    self.stdout.write(self.style.WARNING(f"Invalid ref format: {ref}"))
                continue

            # Check enabled flag
            enabled = spec.get("enabled", False)
            if not sync_all and not enabled:
                skipped += 1
                if not json_mode:
                    self.stdout.write(self.style.WARNING(f"Skipped (disabled): {ref}"))
                continue

            # Determine kind
            kind = spec.get("kind", "processor")

            # Extract registry data
            ref_slug = f"{ns}_{name}"
            inputs_schema = spec.get("inputs", {})
            outputs_decl = spec.get("outputs", [])
            secrets = spec.get("secrets", {})
            required_secrets = secrets.get("required", []) if isinstance(secrets, dict) else secrets or []

            # Image digests
            platforms = spec.get("image", {}).get("platforms", {})
            digest_amd64 = platforms.get("amd64", "")
            digest_arm64 = platforms.get("arm64", "")

            if dry_run:
                if not json_mode:
                    self.stdout.write(f"Would sync: {ref} (enabled={enabled}, kind={kind})")
                continue

            # Create or update
            tool, created_flag = Tool.objects.update_or_create(
                ref=ref,
                defaults={
                    "namespace": ns,
                    "name": name,
                    "version": version,
                    "ref_slug": ref_slug,
                    "kind": kind,
                    "enabled": enabled,
                    "inputs_schema": inputs_schema,
                    "outputs_decl": outputs_decl,
                    "required_secrets": required_secrets,
                    "digest_amd64": digest_amd64,
                    "digest_arm64": digest_arm64,
                },
            )

            if created_flag:
                created += 1
                if not json_mode:
                    self.stdout.write(self.style.SUCCESS(f"Created: {ref}"))
            else:
                updated += 1
                if not json_mode:
                    self.stdout.write(self.style.SUCCESS(f"Updated: {ref}"))

        if json_mode:
            import json

            sys.stdout.write(
                json.dumps(
                    {
                        "status": "success",
                        "created": created,
                        "updated": updated,
                        "skipped": skipped,
                        "errors": errors,
                    }
                )
                + "\n"
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"\nSync complete: {created} created, {updated} updated, {skipped} skipped (disabled)"
                )
            )

    def handle_enable(self, opts):
        """Enable a tool by ref."""
        ref = opts["ref"]
        json_mode = opts["json"]

        try:
            tool = Tool.objects.get(ref=ref)
            tool.enabled = True
            tool.save(update_fields=["enabled"])

            if json_mode:
                import json

                sys.stdout.write(json.dumps({"status": "success", "ref": ref, "enabled": True}) + "\n")
            else:
                self.stdout.write(self.style.SUCCESS(f"Enabled: {ref}"))
        except Tool.DoesNotExist:
            if json_mode:
                import json

                sys.stdout.write(json.dumps({"status": "error", "error": "Tool not found", "ref": ref}) + "\n")
            else:
                raise CommandError(f"Tool not found: {ref}")

    def handle_disable(self, opts):
        """Disable a tool by ref."""
        ref = opts["ref"]
        json_mode = opts["json"]

        try:
            tool = Tool.objects.get(ref=ref)
            tool.enabled = False
            tool.save(update_fields=["enabled"])

            if json_mode:
                import json

                sys.stdout.write(json.dumps({"status": "success", "ref": ref, "enabled": False}) + "\n")
            else:
                self.stdout.write(self.style.SUCCESS(f"Disabled: {ref}"))
        except Tool.DoesNotExist:
            if json_mode:
                import json

                sys.stdout.write(json.dumps({"status": "error", "error": "Tool not found", "ref": ref}) + "\n")
            else:
                raise CommandError(f"Tool not found: {ref}")

    def handle_list(self, opts):
        """List all tools."""
        enabled_only = opts["enabled_only"]
        json_mode = opts["json"]

        qs = Tool.objects.all()
        if enabled_only:
            qs = qs.filter(enabled=True)

        tools = list(qs.order_by("ref"))

        if json_mode:
            import json

            sys.stdout.write(
                json.dumps(
                    {
                        "status": "success",
                        "count": len(tools),
                        "tools": [
                            {
                                "ref": t.ref,
                                "namespace": t.namespace,
                                "name": t.name,
                                "version": t.version,
                                "kind": t.kind,
                                "enabled": t.enabled,
                            }
                            for t in tools
                        ],
                    }
                )
                + "\n"
            )
        else:
            self.stdout.write(f"Found {len(tools)} tools:\n")
            for t in tools:
                status = "✓" if t.enabled else "✗"
                self.stdout.write(f"  {status} {t.ref} ({t.kind})")
