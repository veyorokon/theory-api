"""
List Modal apps and their status.

Usage:
    python manage.py status_modal --env dev [options]
"""

import json
import sys
from django.core.management.base import BaseCommand

from apps.core.modalctl import list_apps


class Command(BaseCommand):
    help = "List Modal apps in environment"

    def add_arguments(self, parser):
        parser.add_argument("--env", required=True, choices=["dev", "staging", "main"], help="Target environment")
        parser.add_argument("--app-name-prefix", help="Filter apps by name prefix")
        parser.add_argument("--json", action="store_true", help="Output only JSON (no human-readable table)")

    def handle(self, *args, **options):
        env = options["env"]
        prefix = options.get("app_name_prefix")
        json_only = options["json"]

        # Log start (unless JSON-only)
        if not json_only:
            self.stdout.write(f"📱 Listing Modal apps in environment: {env}")
            if prefix:
                self.stdout.write(f"🔍 Filter prefix: {prefix}")

        try:
            result = list_apps(env, prefix)

            # Always output canonical JSON
            json_output = json.dumps(result, separators=(",", ":"))
            self.stdout.write(json_output)

            if result["status"] == "success":
                apps = result.get("apps", [])
                count = result.get("count", 0)

                if not json_only:
                    if count == 0:
                        self.stdout.write("📭 No apps found")
                    else:
                        self.stdout.write(f"📊 Found {count} apps:")
                        self.stdout.write("")

                        # Human-readable table
                        if apps:
                            # Headers
                            self.stdout.write(f"{'App Name':<40} {'Functions':<20} {'Last Updated':<20}")
                            self.stdout.write("-" * 80)

                            for app in apps:
                                name = app.get("name", "unknown")[:39]
                                functions = ", ".join(app.get("functions", []))[:19]
                                updated = app.get("last_updated", "unknown")[:19]

                                self.stdout.write(f"{name:<40} {functions:<20} {updated:<20}")
            else:
                if not json_only:
                    self.stderr.write(f"❌ Failed to list apps: {result['error']['message']}")
                sys.exit(1)

        except Exception as e:
            error_result = {"status": "error", "error": {"code": "UNEXPECTED_ERROR", "message": str(e)}}
            self.stdout.write(json.dumps(error_result, separators=(",", ":")))
            if not json_only:
                self.stderr.write(f"❌ Unexpected error: {e}")
            sys.exit(1)
