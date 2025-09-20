"""
Sync secrets to Modal environment.

Usage:
    python manage.py sync_modal_secrets --env dev|staging|main [options]
"""

import json
import os
import sys
from django.core.management.base import BaseCommand

from apps.core.modalctl import ensure_secrets, find_required_secrets_from_registry


class Command(BaseCommand):
    help = "Idempotently sync secrets to Modal environment"

    def add_arguments(self, parser):
        parser.add_argument("--env", required=True, choices=["dev", "staging", "main"], help="Target environment")
        parser.add_argument("--secrets", help="Comma-separated list of secret names (defaults to registry scan)")
        parser.add_argument(
            "--registry-scan", type=bool, default=True, help="Scan registry for required secrets (default: true)"
        )

    def handle(self, *args, **options):
        env = options["env"]

        # Determine which secrets to sync
        if options["secrets"]:
            secret_names = [s.strip() for s in options["secrets"].split(",") if s.strip()]
        elif options["registry_scan"]:
            secret_names = list(find_required_secrets_from_registry())
        else:
            secret_names = []

        if not secret_names:
            result = {
                "status": "success",
                "env": env,
                "secrets": {"created": [], "updated": [], "unchanged": [], "errors": []},
                "message": "No secrets to sync",
            }
            self.stdout.write(json.dumps(result, separators=(",", ":")))
            return

        # Log start
        self.stdout.write(f"🔐 Syncing {len(secret_names)} secrets to Modal env: {env}")
        for name in secret_names:
            self.stdout.write(f"  - {name}")

        # Collect secret values
        secrets_dict = {}
        missing_secrets = []

        for name in secret_names:
            # Try GitHub Actions environment first, then local env
            value = os.getenv(name)

            if value:
                secrets_dict[name] = value
                # Never log actual values, only metadata
                self.stdout.write(f"  ✓ {name} (len={len(value)})")
            else:
                missing_secrets.append(name)
                self.stdout.write(f"  ✗ {name} (not found in environment)")

        if missing_secrets:
            if env in ("staging", "main"):
                # Missing secrets in prod environments is an error
                error_result = {
                    "status": "error",
                    "error": {
                        "code": "MISSING_SECRETS",
                        "message": f"Missing required secrets: {', '.join(missing_secrets)}",
                    },
                }
                self.stdout.write(json.dumps(error_result, separators=(",", ":")))
                self.stderr.write(f"❌ Missing secrets in {env}: {', '.join(missing_secrets)}")
                sys.exit(1)
            else:
                # In dev, warn but continue with available secrets
                self.stdout.write(f"⚠️  Proceeding without missing secrets in dev: {', '.join(missing_secrets)}")

        if not secrets_dict:
            result = {
                "status": "success",
                "env": env,
                "secrets": {"created": [], "updated": [], "unchanged": [], "errors": []},
                "message": "No secrets available to sync",
            }
            self.stdout.write(json.dumps(result, separators=(",", ":")))
            return

        try:
            result = ensure_secrets(env, secrets_dict)

            # Always output canonical JSON
            json_output = json.dumps(result, separators=(",", ":"))
            self.stdout.write(json_output)

            # Log summary
            secrets_info = result.get("secrets", {})
            updated_count = len(secrets_info.get("updated", []))
            error_count = len(secrets_info.get("errors", []))

            if result["status"] == "success":
                self.stdout.write(f"✅ Synced {updated_count} secrets to Modal {env}")
            elif result["status"] == "partial":
                self.stdout.write(f"⚠️  Partial sync: {updated_count} synced, {error_count} errors")
                sys.exit(1)
            else:
                self.stderr.write("❌ Secret sync failed")
                sys.exit(1)

        except Exception as e:
            error_result = {"status": "error", "error": {"code": "UNEXPECTED_ERROR", "message": str(e)}}
            self.stdout.write(json.dumps(error_result, separators=(",", ":")))
            self.stderr.write(f"❌ Unexpected error: {e}")
            sys.exit(1)
