"""
Thin orchestrator for Modal function deployment using the committed module.

Runs `modal deploy` against top-level `modal_app` module with portable paths.
"""
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from pathlib import Path
import subprocess
import os


class Command(BaseCommand):
    help = "Deploy Modal app functions from committed module."

    def add_arguments(self, parser):
        parser.add_argument("--env", default="dev", help="Modal environment (dev|staging|main)")

    def handle(self, *args, **options):
        env = options["env"]

        # Verify Modal credentials
        if not os.getenv("MODAL_TOKEN_ID") or not os.getenv("MODAL_TOKEN_SECRET"):
            raise CommandError("MODAL_TOKEN_ID and MODAL_TOKEN_SECRET must be set in env")

        # Use Django's BASE_DIR (portable)
        code_dir = Path(settings.BASE_DIR)
        module = "modal_app"
        
        # Sanity check that modal_app.py exists
        modal_app_path = code_dir / f"{module}.py"
        if not modal_app_path.exists():
            raise CommandError(f"Cannot find {modal_app_path}. Expected at project code root.")

        self.stdout.write(f"🚀 Deploying Modal app module...")
        self.stdout.write(f"📦 Environment: {env}")
        self.stdout.write(f"📁 Working directory: {code_dir}")

        # Keep environment minimal (no DJANGO_SETTINGS_MODULE needed for modal deploy)
        child_env = os.environ.copy()
        child_env.setdefault("MODAL_ENVIRONMENT", env)

        try:
            subprocess.run(
                ["modal", "deploy", "--env", env, "-m", module],
                check=True,
                cwd=str(code_dir),
                env=child_env,
            )
            self.stdout.write("✅ Modal deployment completed")
        except subprocess.CalledProcessError as e:
            raise CommandError(f"Modal deploy failed (exit {e.returncode})") from e
