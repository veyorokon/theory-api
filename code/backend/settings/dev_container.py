"""
Docker Compose development settings.

Used when running Django inside a docker container with docker-compose.
Database and MinIO are also containers on the same docker network.
"""

from .base import *
import dj_database_url

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env("DJANGO_SECRET_KEY", "django-insecure-dev-container-key")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ["*"]

# Database: postgres container (required for docker-compose)
DATABASE_URL = environ_setting("DATABASE_URL")
DATABASES = {"default": dj_database_url.parse(DATABASE_URL)}

# Storage: MinIO container (override endpoint to use docker network hostname)
# Inherited STORAGE dict from base.py, just update the endpoint
STORAGE["MINIO"]["ENDPOINT"] = "minio:9000"

# Modal environment name for Function.from_name(..., environment_name=...)
# Shimmed to APP_ENV for consistency
MODAL_ENVIRONMENT = APP_ENV
