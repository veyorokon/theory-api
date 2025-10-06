from .base import *
import dj_database_url

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = environ_setting("SECRET_KEY")

DEBUG = False

ALLOWED_HOSTS = environ_setting("ALLOWED_HOSTS", "").split(",")

# Database
DATABASE_URL = environ_setting("DATABASE_URL")
DATABASES = {"default": dj_database_url.parse(DATABASE_URL)}

# Security: HTTPS-only cookies in production
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True  # Redirect HTTP to HTTPS
SECURE_HSTS_SECONDS = 31536000  # 1 year HSTS
SECURE_HSTS_INCLUDE_SUBDOMAINS = True

# Storage settings are configured in base.py using STORAGE dict
# In production, set STORAGE_BACKEND=s3 and ARTIFACTS_BUCKET/REGION via env vars
# AWS credentials are sourced from environment (preferably IAM role)
MODAL_ENVIRONMENT = env("MODAL_ENVIRONMENT", default="staging", required=MODAL_ENABLED)
