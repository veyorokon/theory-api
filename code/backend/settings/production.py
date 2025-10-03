from .base import *
import dj_database_url

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = environ_setting("SECRET_KEY")

DEBUG = False

ALLOWED_HOSTS = environ_setting("ALLOWED_HOSTS", "").split(",")

# Database
DATABASE_URL = environ_setting("DATABASE_URL")
DATABASES = {"default": dj_database_url.parse(DATABASE_URL)}

# Storage settings are configured in base.py using STORAGE dict
# In production, set STORAGE_BACKEND=s3 and ARTIFACTS_BUCKET/REGION via env vars
# AWS credentials are sourced from environment (preferably IAM role)
