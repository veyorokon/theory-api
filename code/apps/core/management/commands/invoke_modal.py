"""
Generic Modal function invocation for debugging.

Usage:
    python manage.py invoke_modal --env dev --app-name xyz --fn run --payload-json '{...}'
"""

import json
import sys
from django.core.management.base import BaseCommand

from apps.core.modalctl import call, resolve_app_name


class Command(BaseCommand):
    help = "Generic Modal function invocation"

    def add_arguments(self, parser):
        parser.add_argument("--env", required=True, choices=["dev", "staging", "main"], help="Target environment")
        parser.add_argument("--app-name", help="Modal app name (defaults to convention)")
        parser.add_argument("--fn", required=True, choices=["run", "smoke"], help="Function name to call")
        parser.add_argument("--payload-json", required=True, help="JSON payload to send to function")
        parser.add_argument("--timeout", type=int, default=900, help="Call timeout in seconds (default: 900)")

    def handle(self, *args, **options):
        env = options["env"]
        app_name = resolve_app_name(env, options.get("app_name"))
        fn_name = options["fn"]
        payload_json = options["payload_json"]
        timeout = options["timeout"]

        # Parse payload
        try:
            payload = json.loads(payload_json)
        except json.JSONDecodeError as e:
            self.stderr.write(f"❌ Invalid payload JSON: {e}")
            sys.exit(1)

        # Log start
        self.stdout.write(f"📞 Invoking Modal function: {app_name}::{fn_name}")
        self.stdout.write(f"📦 Environment: {env}")
        self.stdout.write(f"📄 Payload keys: {list(payload.keys())}")

        try:
            result = call(env, app_name, fn_name, payload, timeout)

            # Always output canonical JSON
            json_output = json.dumps(result, separators=(",", ":"))
            self.stdout.write(json_output)

            if result["status"] == "success":
                self.stdout.write("✅ Function call completed")

                # Pretty print response if it's JSON
                response = result.get("response", "")
                if response:
                    try:
                        parsed_response = json.loads(response)
                        self.stdout.write("📋 Response (pretty):")
                        self.stdout.write(json.dumps(parsed_response, indent=2))
                    except json.JSONDecodeError:
                        self.stdout.write(f"📋 Response (raw): {response}")
            else:
                self.stderr.write(f"❌ Function call failed: {result['error']['message']}")
                sys.exit(1)

        except Exception as e:
            error_result = {"status": "error", "error": {"code": "UNEXPECTED_ERROR", "message": str(e)}}
            self.stdout.write(json.dumps(error_result, separators=(",", ":")))
            self.stderr.write(f"❌ Unexpected error: {e}")
            sys.exit(1)
