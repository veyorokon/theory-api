"""
Delete a specific Modal app.

Usage:
    python manage.py destroy_modal --env dev --app-name xyz [options]
"""

import json
import sys
from django.core.management.base import BaseCommand

from apps.core.modalctl import delete_app, resolve_app_name


class Command(BaseCommand):
    help = "Delete a Modal app"

    def add_arguments(self, parser):
        parser.add_argument("--env", required=True, choices=["dev", "staging", "main"], help="Target environment")
        parser.add_argument("--app-name", help="Modal app name (defaults to convention)")
        parser.add_argument("--force", action="store_true", help="Skip confirmation prompt")

    def handle(self, *args, **options):
        env = options["env"]
        app_name = resolve_app_name(env, options.get("app_name"))
        force = options["force"]

        # Log start
        self.stdout.write(f"🗑️  Destroying Modal app: {app_name}")
        self.stdout.write(f"📦 Environment: {env}")

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
