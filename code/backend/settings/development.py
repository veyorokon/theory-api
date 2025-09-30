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

# Storage settings for development (MinIO)
STORAGE_BACKEND = "minio"
MINIO_ENDPOINT = os.environ.get("MINIO_STORAGE_ENDPOINT", "minio.local:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_STORAGE_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.environ.get("MINIO_STORAGE_SECRET_KEY", "minioadmin")
MINIO_USE_HTTPS = os.environ.get("MINIO_STORAGE_USE_HTTPS", "false").lower() == "true"
DEFAULT_FILE_STORAGE_BUCKET = os.environ.get("MINIO_STORAGE_MEDIA_BUCKET_NAME", "media")

# Django file storage
DEFAULT_FILE_STORAGE = "apps.storage.backends.VendorNeutralStorage"
MEDIA_URL = f"http://{MINIO_ENDPOINT}/media/"


LLM_SETTINGS = {
    "default_model": os.environ.get("LLM_MODEL_DEFAULT", "openai/gpt-4o-mini"),
    "api_base": os.environ.get("LLM_API_BASE", ""),
}
