"""
Delete a specific Modal app.

Usage:
    python manage.py destroy_modal --ref llm/litellm@1 [options]
"""

import json
import sys

from apps.core.management.commands._modal_base import ModalCommand
from apps.core.modalctl import delete_app


class Command(ModalCommand):
    help = "Delete a Modal app"

    def add_modal_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Skip confirmation prompt")

    def handle(self, *args, **options):
        ctx = self.get_ctx(options)
        app_name = ctx.app_name
        env = ctx.environment
        processor_ref = ctx.processor_ref
        force = options["force"]

        # Log start
        self.stdout.write(f"🗑️  Destroying Modal app: {app_name}")
        self.stdout.write(f"📦 Environment: {env}")
        if processor_ref:
            self.stdout.write(f"🔧 Processor: {processor_ref}")

        # Safety confirmation
        if not force:
            if env in ("staging", "main"):
                self.stdout.write(f"⚠️  WARNING: Deleting app in {env} environment!")

            confirm = input(f"Delete app '{app_name}' in {env}? [y/N]: ")
            if confirm.lower() not in ("y", "yes"):
                self.stdout.write("Deletion cancelled")
                return

        try:
            result = delete_app(env, app_name)

            # Always output canonical JSON
            json_output = json.dumps(result, separators=(",", ":"))
            self.stdout.write(json_output)

            if result["status"] == "success":
                if result.get("deleted"):
                    self.stdout.write(f"✅ App deleted: {app_name}")
                else:
                    self.stdout.write(f"✅ App already deleted: {app_name}")
            else:
                self.stderr.write(f"❌ Failed to delete app: {result['error']['message']}")
                sys.exit(1)

        except Exception as e:
            error_result = {"status": "error", "error": {"code": "UNEXPECTED_ERROR", "message": str(e)}}
            self.stdout.write(json.dumps(error_result, separators=(",", ":")))
            self.stderr.write(f"❌ Unexpected error: {e}")
            sys.exit(1)
