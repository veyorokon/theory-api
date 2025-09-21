"""
Deploy Modal functions to an environment.

Usage:
    python manage.py deploy_modal --env dev|staging|main --ref llm/litellm@1 [options]
"""

import json
import sys
from django.core.management.base import BaseCommand

from apps.core.modalctl import deploy, resolve_app_name


class Command(BaseCommand):
    help = "Deploy Modal functions to environment"

    def add_arguments(self, parser):
        parser.add_argument("--env", required=True, choices=["dev", "staging", "main"], help="Target environment")
        parser.add_argument("--ref", required=True, help="Processor reference (e.g., llm/litellm@1)")
        parser.add_argument("--app-name", help="Override app name (defaults to canonical ref-based name)")
        parser.add_argument(
            "--from-path", default="code/modal_app.py", help="Path to modal_app.py (default: code/modal_app.py)"
        )
        parser.add_argument("--timeout", type=int, default=900, help="Deployment timeout in seconds (default: 900)")
        parser.add_argument("--force", action="store_true", help="Proceed without confirmation")

    def handle(self, *args, **options):
        env = options["env"]
        processor_ref = options["ref"]
        app_name = resolve_app_name(env, preferred=options.get("app_name"), processor_ref=processor_ref)
        from_path = options["from_path"]
        timeout = options["timeout"]
        force = options["force"]

        # Log start
        self.stdout.write(f"🚀 Deploying Modal app: {app_name}")
        self.stdout.write(f"📦 Environment: {env}")
        self.stdout.write(f"📁 From: {from_path}")
        self.stdout.write(f"🔧 Processor: {processor_ref}")

        # Confirmation for non-dev environments
        if env in ("staging", "main") and not force:
            confirm = input(f"Deploy to {env} environment? [y/N]: ")
            if confirm.lower() not in ("y", "yes"):
                self.stdout.write("Deployment cancelled")
                return

        try:
            result = deploy(
                env=env, app_name=app_name, from_path=from_path, timeout=timeout, processor_ref=processor_ref
            )

            # Always output canonical JSON
            json_output = json.dumps(result, separators=(",", ":"))
            self.stdout.write(json_output)

            # Exit with appropriate code
            if result["status"] == "success":
                self.stdout.write("✅ Modal deployment completed", ending="")
            else:
                self.stderr.write(f"❌ Deployment failed: {result['error']['message']}")
                sys.exit(1)

        except Exception as e:
            error_result = {"status": "error", "error": {"code": "UNEXPECTED_ERROR", "message": str(e)}}
            self.stdout.write(json.dumps(error_result, separators=(",", ":")))
            self.stderr.write(f"❌ Unexpected error: {e}")
            sys.exit(1)
