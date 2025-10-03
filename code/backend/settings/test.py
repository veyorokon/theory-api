"""
Test settings for theory_api project.

Uses PostgreSQL via docker-compose for acceptance/property tests.
"""

from .development import *  # noqa
import os
from urllib.parse import urlparse

# Use TEST_DATABASE_URL if set; otherwise default to localhost compose
url = os.getenv("TEST_DATABASE_URL", "postgresql://postgres:postgres_password@127.0.0.1:5432/postgres")
parsed = urlparse(url)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": parsed.path.lstrip("/"),
        "USER": parsed.username,
        "PASSWORD": parsed.password,
        "HOST": parsed.hostname,
        "PORT": parsed.port or 5432,
    }
}

# Test-specific settings
SECRET_KEY = "test-secret-key-not-for-production"

# Disable migrations for faster test runs if needed
# MIGRATION_MODULES = {app: None for app in LOCAL_APPS}

# Logging for debugging tests
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "loggers": {
        "django.db.backends": {
            "level": "WARNING",  # Set to DEBUG to see SQL queries
            "handlers": ["console"],
        },
    },
}
