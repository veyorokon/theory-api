from .base import *
import dj_database_url

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = environ_setting("DJANGO_SECRET_KEY")

DEBUG = False

ALLOWED_HOSTS = environ_setting("ALLOWED_HOSTS", "").split(",")

# Database
DATABASE_URL = environ_setting("DATABASE_URL")
DATABASES = {"default": dj_database_url.parse(DATABASE_URL)}

# Security: HTTPS-only cookies in production
SECURE_SSL_REDIRECT = env("SECURE_SSL_REDIRECT", default="true", cast=bool)
CSRF_COOKIE_SECURE = SECURE_SSL_REDIRECT
SESSION_COOKIE_SECURE = SECURE_SSL_REDIRECT
SECURE_HSTS_SECONDS = 31536000 if SECURE_SSL_REDIRECT else 0  # 1 year HSTS
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_SSL_REDIRECT

# Storage settings are configured in base.py using STORAGE dict
# In production, set STORAGE_BACKEND=s3 and ARTIFACTS_BUCKET/REGION via env vars
# AWS credentials are sourced from environment (preferably IAM role)
MODAL_ENVIRONMENT = env("MODAL_ENVIRONMENT", default="main", required=MODAL_ENABLED)
