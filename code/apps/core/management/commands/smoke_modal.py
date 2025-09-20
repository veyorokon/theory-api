"""
Post-deploy validation using Modal smoke function.

Usage:
    python manage.py smoke_modal --env dev --app-name xyz --ref llm/litellm@1 [options]
"""

import json
import sys
from django.core.management.base import BaseCommand

from apps.core.modalctl import call, resolve_app_name


class Command(BaseCommand):
    help = "Post-deploy validation via Modal smoke function"

    def add_arguments(self, parser):
        parser.add_argument("--env", required=True, choices=["dev", "staging", "main"], help="Target environment")
        parser.add_argument("--app-name", help="Modal app name (defaults to convention)")
        parser.add_argument("--ref", required=True, help="Processor reference (e.g., llm/litellm@1)")
        parser.add_argument("--model", help="Model name for processor (optional)")
        parser.add_argument("--inputs-json", help="Custom inputs JSON (defaults to minimal test payload)")
        parser.add_argument("--timeout", type=int, default=120, help="Call timeout in seconds (default: 120)")

    def handle(self, *args, **options):
        env = options["env"]
        app_name = resolve_app_name(env, preferred=options.get("app_name"))
        ref = options["ref"]
        model = options.get("model")
        inputs_json = options.get("inputs_json")
        timeout = options["timeout"]

        # Build minimal test payload
        if inputs_json:
            try:
                custom_inputs = json.loads(inputs_json)
            except json.JSONDecodeError as e:
                self.stderr.write(f"❌ Invalid inputs JSON: {e}")
                sys.exit(1)
        else:
            # Default minimal payload based on processor type
            if "llm/" in ref:
                custom_inputs = {
                    "schema": "v1",
                    "params": {"messages": [{"role": "user", "content": "hello from smoke test"}]},
                }
                if model:
                    custom_inputs["model"] = model
            elif "replicate/" in ref:
                custom_inputs = {"schema": "v1", "params": {"prompt": "hello from smoke test"}}
                if model:
                    custom_inputs["model"] = model
            else:
                custom_inputs = {"schema": "v1"}

        # Force mode=mock for smoke tests
        payload = {**custom_inputs, "mode": "mock", "ref": ref}

        # Log start
        self.stdout.write(f"💨 Smoke testing Modal app: {app_name}")
        self.stdout.write(f"📦 Environment: {env}")
        self.stdout.write(f"🔧 Processor: {ref}")
        self.stdout.write("🎯 Mode: mock (forced)")

        try:
            # Call the smoke function (always uses mode=mock)
            result = call(env, app_name, "smoke", payload, timeout)

            # Always output canonical JSON
            json_output = json.dumps(result, separators=(",", ":"))
            self.stdout.write(json_output)

            if result["status"] == "success":
                # Try to parse the response as envelope
                response = result.get("response", "")
                try:
                    envelope = json.loads(response) if response else {}
                    if envelope.get("status") == "success":
                        self.stdout.write("✅ Smoke test passed")
                    elif envelope.get("status") == "error":
                        self.stderr.write(
                            f"❌ Processor returned error: {envelope.get('error', {}).get('message', 'Unknown')}"
                        )
                        sys.exit(1)
                    else:
                        self.stdout.write("✅ Smoke test completed (non-envelope response)")
                except json.JSONDecodeError:
                    self.stdout.write("✅ Smoke test completed (non-JSON response)")
            else:
                self.stderr.write(f"❌ Smoke test failed: {result['error']['message']}")
                sys.exit(1)

        except Exception as e:
            error_result = {"status": "error", "error": {"code": "UNEXPECTED_ERROR", "message": str(e)}}
            self.stdout.write(json.dumps(error_result, separators=(",", ":")))
            self.stderr.write(f"❌ Unexpected error: {e}")
            sys.exit(1)
