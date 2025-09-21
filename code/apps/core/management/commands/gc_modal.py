"""
Garbage collect stale dev Modal apps.

Usage:
    python manage.py gc_modal --env dev --older-than-days 7 [options]
"""

import json
import sys
from datetime import datetime, timedelta, timezone, UTC
from django.core.management.base import BaseCommand

from apps.core.modalctl import list_apps, delete_app


class Command(BaseCommand):
    help = "Garbage collect stale Modal apps"

    def add_arguments(self, parser):
        parser.add_argument("--env", required=True, choices=["dev", "staging", "main"], help="Target environment")
        parser.add_argument(
            "--app-name-prefix", default="theory-dev-", help="App name prefix to filter (default: theory-dev-)"
        )
        parser.add_argument("--older-than-days", type=int, required=True, help="Delete apps older than N days")
        parser.add_argument(
            "--dry-run", action="store_true", help="Show what would be deleted without actually deleting"
        )
        parser.add_argument("--force", action="store_true", help="Actually delete apps (required for real deletion)")

    def handle(self, *args, **options):
        env = options["env"]
        prefix = options["app_name_prefix"]
        older_than_days = options["older_than_days"]
        dry_run = options["dry_run"]
        force = options["force"]

        # Safety: only allow gc in dev environment
        if env != "dev":
            self.stderr.write(f"❌ Garbage collection only allowed in dev environment, not {env}")
            sys.exit(1)

        # Log start
        self.stdout.write(f"🗑️  Garbage collecting Modal apps in: {env}")
        self.stdout.write(f"🔍 Prefix filter: {prefix}")
        self.stdout.write(f"📅 Older than: {older_than_days} days")
        if dry_run:
            self.stdout.write("🔍 DRY RUN: No apps will be deleted")

        try:
            # List apps with prefix filter
            result = list_apps(env, prefix)

            if result["status"] != "success":
                self.stderr.write(f"❌ Failed to list apps: {result['error']['message']}")
                sys.exit(1)

            apps = result.get("apps", [])
            cutoff_date = datetime.now(UTC) - timedelta(days=older_than_days)

            # Find stale apps
            stale_apps = []
            for app in apps:
                # Modal CLI uses "Created at" field, not "last_updated"
                created_at_str = app.get("Created at", "")
                app_name = app.get("Description", app.get("App ID", "unknown"))
                try:
                    # Parse Modal's datetime format: "2025-09-20 20:20:21-04:00"
                    created_at = datetime.fromisoformat(created_at_str)
                    if created_at < cutoff_date:
                        stale_apps.append(app)
                except (ValueError, AttributeError):
                    # If we can't parse the date, skip this app
                    self.stdout.write(f"⚠️  Skipping {app_name}: couldn't parse Created at '{created_at_str}'")
                    continue

            # Output results
            gc_result = {
                "status": "success",
                "env": env,
                "total_apps": len(apps),
                "stale_apps": len(stale_apps),
                "cutoff_date": cutoff_date.isoformat(),
                "dry_run": dry_run,
                "deleted": [],
                "errors": [],
            }

            if not stale_apps:
                gc_result["message"] = "No stale apps found"
                self.stdout.write(json.dumps(gc_result, separators=(",", ":")))
                self.stdout.write("✅ No stale apps to clean up")
                return

            self.stdout.write(f"📊 Found {len(stale_apps)} stale apps:")
            for app in stale_apps:
                name = app.get("Description", app.get("App ID", "unknown"))
                created = app.get("Created at", "unknown")
                self.stdout.write(f"  - {name} (created: {created})")

            if dry_run:
                gc_result["message"] = f"Would delete {len(stale_apps)} apps (dry run)"
                self.stdout.write(json.dumps(gc_result, separators=(",", ":")))
                self.stdout.write(f"🔍 DRY RUN: Would delete {len(stale_apps)} apps")
                return

            if not force:
                self.stderr.write("❌ Use --force to actually delete apps")
                sys.exit(1)

            # When --force is used, skip interactive confirmation
            self.stdout.write(f"🚀 Force deleting {len(stale_apps)} stale apps")

            # Delete stale apps
            for app in stale_apps:
                app_name = app.get("Description", app.get("App ID"))
                if not app_name:
                    continue

                delete_result = delete_app(env, app_name)
                if delete_result["status"] == "success":
                    gc_result["deleted"].append(app_name)
                    self.stdout.write(f"✅ Deleted: {app_name}")
                else:
                    error_msg = delete_result.get("error", {}).get("message", "Unknown error")
                    gc_result["errors"].append(f"{app_name}: {error_msg}")
                    self.stderr.write(f"❌ Failed to delete {app_name}: {error_msg}")

            # Final output
            self.stdout.write(json.dumps(gc_result, separators=(",", ":")))

            deleted_count = len(gc_result["deleted"])
            error_count = len(gc_result["errors"])

            if error_count == 0:
                self.stdout.write(f"✅ Garbage collection completed: {deleted_count} apps deleted")
            else:
                self.stdout.write(f"⚠️  Partial success: {deleted_count} deleted, {error_count} errors")
                sys.exit(1)

        except Exception as e:
            error_result = {"status": "error", "error": {"code": "UNEXPECTED_ERROR", "message": str(e)}}
            self.stdout.write(json.dumps(error_result, separators=(",", ":")))
            self.stderr.write(f"❌ Unexpected error: {e}")
            sys.exit(1)
