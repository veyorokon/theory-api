"""
Tail recent logs for a Modal function.

Usage:
    python manage.py logs_modal --env dev --app-name xyz --fn run [options]
"""

import json
import sys
from django.core.management.base import BaseCommand

from apps.core.modalctl import tail_logs, resolve_app_name


class Command(BaseCommand):
    help = "Tail recent logs for Modal function"

    def add_arguments(self, parser):
        parser.add_argument("--env", required=True, choices=["dev", "staging", "main"], help="Target environment")
        parser.add_argument("--app-name", help="Modal app name (defaults to convention)")
        parser.add_argument("--fn", required=True, choices=["run", "smoke"], help="Function name")
        parser.add_argument("--since-min", type=int, default=30, help="Minutes of history to fetch (default: 30)")
        parser.add_argument("--limit", type=int, default=200, help="Max number of log lines (default: 200)")

    def handle(self, *args, **options):
        env = options["env"]
        app_name = resolve_app_name(env, options.get("app_name"))
        fn_name = options["fn"]
        since_min = options["since_min"]
        limit = options["limit"]

        # Log start
        self.stdout.write(f"📋 Fetching logs for: {app_name}::{fn_name}")
        self.stdout.write(f"📦 Environment: {env}")
        self.stdout.write(f"⏰ Last {since_min} minutes, max {limit} lines")
        self.stdout.write("-" * 60)

        try:
            result = tail_logs(env, app_name, fn_name, since_min, limit)

            # Always output canonical JSON first
            json_output = json.dumps(result, separators=(",", ":"))
            self.stdout.write(json_output)

            if result["status"] == "success":
                logs = result.get("logs", [])
                stderr = result.get("stderr", "")

                self.stdout.write(f"📊 Found {len(logs)} log lines")
                self.stdout.write("")

                # Output logs with simple formatting
                for line in logs:
                    self.stdout.write(line)

                if stderr:
                    self.stdout.write("")
                    self.stdout.write("🔥 Stderr:")
                    self.stdout.write(stderr)

                self.stdout.write("")
                self.stdout.write("✅ Logs retrieved")
            else:
                self.stderr.write(f"❌ Failed to fetch logs: {result['error']['message']}")
                sys.exit(1)

        except Exception as e:
            error_result = {"status": "error", "error": {"code": "UNEXPECTED_ERROR", "message": str(e)}}
            self.stdout.write(json.dumps(error_result, separators=(",", ":")))
            self.stderr.write(f"❌ Unexpected error: {e}")
            sys.exit(1)
