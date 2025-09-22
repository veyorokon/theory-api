"""
Deploy a Modal app for a processor ref and environment.

Usage:
    python manage.py deploy_modal --ref llm/litellm@1 --env dev [options]
"""

import json
import os
from django.core.management.base import BaseCommand, CommandError
from apps.core.management.commands._modal_common import compute_modal_context
from apps.core.modalctl import deploy


class Command(BaseCommand):
    help = "Deploy a Modal app for a processor ref and environment"

    def add_arguments(self, parser):
        parser.add_argument("--ref", required=True, help="Processor reference (e.g., llm/litellm@1)")
        parser.add_argument("--env", choices=["dev", "staging", "main"], default="dev", help="Target environment")
        parser.add_argument("--image-override", help="Override image for dev (bypasses pins)")
        parser.add_argument("--app-rev", help="App revision for cache-busting")

    def handle(self, *args, **options):
        ref = options["ref"]
        env = options["env"]
        image_override = options.get("image_override")
        app_rev = options.get("app_rev")

        # Only allow image override in dev environment
        if image_override and env != "dev":
            raise CommandError("--image-override only allowed in dev environment (staging/main must use pins)")

        try:
            # Use consistent naming
            ctx = compute_modal_context(processor_ref=ref)
            app_name = ctx.app_name

            # Set environment variables for Modal app
            env_exports = dict(os.environ)
            if app_rev:
                env_exports["APP_REV"] = app_rev

            # If image override provided, temporarily override IMAGE_REF
            if image_override:
                env_exports["IMAGE_REF"] = image_override
                self.stderr.write(f"⚠️ Using image override: {image_override}")

            # Deploy using existing modalctl helper
            result = deploy(
                env=env,
                app_name=app_name,
                from_path="modal_app.py",  # Standard location
                processor_ref=ref,
                timeout=900,
            )

            # Output result
            self.stdout.write(json.dumps(result, separators=(",", ":")))

            if result["status"] == "success":
                self.stderr.write(f"✅ Deployed {app_name} to {env}")
            else:
                self.stderr.write(f"❌ Deploy failed: {result.get('error', {}).get('message', 'Unknown error')}")
                raise CommandError("Deployment failed")

        except Exception as e:
            raise CommandError(f"Failed to deploy Modal app: {e}")
