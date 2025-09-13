"""
Unit test settings for theory_api project.

Uses SQLite for fast, isolated unit tests.
"""

from .base import *  # noqa

# Hermetic settings for fast unit tests
DEBUG = False

# Use SQLite for unit tests (fast, no external dependencies)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Fast, in-memory backends for unit tests
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Use in-memory channel layer for unit tests
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

# Test-specific settings
SECRET_KEY = "test-secret-key-not-for-production-unit-tests"

# Disable migrations for faster test runs
MIGRATION_MODULES = {
    "core": None,
    "storage": None,
    "plans": None,
    "ledger": None,
    "artifacts": None,
    "runtime": None,
}

# Minimal logging for unit tests
LOGGING = {
    "version": 1,
    "disable_existing_loggers": True,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "loggers": {
        "django": {
            "level": "WARNING",
            "handlers": ["console"],
        },
    },
}
