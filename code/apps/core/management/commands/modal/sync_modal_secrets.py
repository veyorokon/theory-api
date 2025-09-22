"""
Sync required secrets (from registry) into a Modal environment.

Usage:
    python manage.py sync_modal_secrets --env dev [options]
"""

import json
import os
from django.core.management.base import BaseCommand, CommandError
from apps.core.modalctl import find_required_secrets_from_registry, ensure_secrets


class Command(BaseCommand):
    help = "Sync required secrets (from registry) into a Modal environment"

    def add_arguments(self, parser):
        parser.add_argument("--env", choices=["dev", "staging", "main"], default="dev", help="Target environment")
        parser.add_argument(
            "--fail-on-missing", action="store_true", help="Exit with error if required secrets are missing"
        )
        parser.add_argument(
            "--secrets", nargs="*", help="Specific secret names to sync (defaults to all from registry)"
        )
        parser.add_argument(
            "--registry-scan",
            type=str,
            choices=["true", "false"],
            default="true",
            help="Scan registry for required secrets",
        )

    def handle(self, *args, **options):
        env = options["env"]
        fail_on_missing = options["fail_on_missing"]
        explicit_secrets = options.get("secrets", [])
        registry_scan = options["registry_scan"] == "true"

        try:
            # Determine which secrets to sync
            if explicit_secrets:
                secret_names = set(explicit_secrets)
                self.stderr.write(f"🔑 Syncing explicit secrets: {sorted(secret_names)}")
            elif registry_scan:
                secret_names = find_required_secrets_from_registry()
                self.stderr.write(f"🔍 Found {len(secret_names)} secrets in registry")
            else:
                secret_names = set()

            if not secret_names:
                result = {"status": "success", "env": env, "message": "No secrets to sync"}
                self.stdout.write(json.dumps(result, separators=(",", ":")))
                self.stderr.write("✅ No secrets to sync")
                return

            # Check which secrets are available in environment
            missing_secrets = []
            available_secrets = {}

            for name in sorted(secret_names):
                value = os.getenv(name)
                if value:
                    available_secrets[name] = value
                else:
                    missing_secrets.append(name)

            if missing_secrets:
                self.stderr.write(f"⚠️ Missing secrets in environment: {missing_secrets}")
                # Auto-enforce fail-on-missing for staging/main environments
                if fail_on_missing or env in ["staging", "main"]:
                    raise CommandError(f"Required secrets missing from environment: {missing_secrets}")

            if not available_secrets:
                result = {"status": "success", "env": env, "message": "No secrets available to sync"}
                self.stdout.write(json.dumps(result, separators=(",", ":")))
                self.stderr.write("⚠️ No secrets available in environment")
                return

            # Sync available secrets to Modal
            self.stderr.write(f"🔄 Syncing {len(available_secrets)} secrets to Modal {env}")

            result = ensure_secrets(env, available_secrets)

            # Always output canonical JSON result
            self.stdout.write(json.dumps(result, separators=(",", ":")))

            # Log summary to stderr
            if result["status"] == "success":
                secrets_info = result.get("secrets", {})
                updated = len(secrets_info.get("updated", []))
                errors = len(secrets_info.get("errors", []))

                if errors > 0:
                    self.stderr.write(f"⚠️ Completed with {errors} errors")
                else:
                    self.stderr.write(f"✅ Successfully synced {updated} secrets")
            else:
                self.stderr.write(f"❌ Sync failed: {result.get('error', {}).get('message', 'Unknown error')}")

        except Exception as e:
            raise CommandError(f"Failed to sync Modal secrets: {e}")
