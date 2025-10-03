import os
from .base import *
import dj_database_url

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get("SECRET_KEY", "django-insecure-dev-key-only-for-development")

# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL:
    DATABASES = {"default": dj_database_url.parse(DATABASE_URL)}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ["*"]

# Graphene settings
GRAPHENE = {
    "SCHEMA": "backend.schema.schema",
    "MIDDLEWARE": [
        "graphene_django.debug.DjangoDebugMiddleware",
    ],
}

# Storage and LLM settings are configured in base.py
