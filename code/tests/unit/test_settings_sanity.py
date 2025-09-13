"""
Settings sanity test - ensures unit tests use hermetic SQLite configuration.

This canary test catches configuration drift where unit tests accidentally
use PostgreSQL or other external services.
"""

import os
import pytest
from django.conf import settings


@pytest.mark.unit
def test_unit_settings_are_sqlite_and_unittest_module():
    """Ensure the unit lane is pointing at the unittest settings module."""
    dj_settings = os.environ.get("DJANGO_SETTINGS_MODULE", "")
    assert dj_settings.endswith(".unittest"), (
        f"Expected DJANGO_SETTINGS_MODULE to be unittest settings, got: {dj_settings}"
    )

    # Ensure the DB engine is SQLite (hermetic + fast)
    engine = settings.DATABASES["default"]["ENGINE"]
    assert engine == "django.db.backends.sqlite3", (
        f"Unit tests must use SQLite, got engine: {engine}"
    )

    # A couple of cheap hermeticity checks that commonly drift
    email_backend = getattr(settings, "EMAIL_BACKEND", "")
    assert "locmem" in email_backend, (
        f"Unit tests should use locmem email backend, got: {email_backend}"
    )

    caches = getattr(settings, "CACHES", {})
    default_cache = caches.get("default", {}).get("BACKEND", "")
    assert "locmem" in default_cache, (
        f"Unit tests should use locmem cache, got: {default_cache or caches}"
    )

    # Ensure DEBUG is off for unit tests (performance)
    assert not settings.DEBUG, "DEBUG should be False for unit tests"