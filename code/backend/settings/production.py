import os
from .base import *
import dj_database_url

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = environ_setting("SECRET_KEY")

DEBUG = False

ALLOWED_HOSTS = environ_setting("ALLOWED_HOSTS", "").split(",")

# Database
DATABASE_URL = environ_setting('DATABASE_URL')
DATABASES = {
    'default': dj_database_url.parse(DATABASE_URL)
}

# Storage settings for production (S3)
STORAGE_BACKEND = 's3'
AWS_ACCESS_KEY_ID = environ_setting('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = environ_setting('AWS_SECRET_ACCESS_KEY')
AWS_S3_REGION_NAME = environ_setting('AWS_S3_REGION_NAME', 'us-east-1')
DEFAULT_FILE_STORAGE_BUCKET = environ_setting('AWS_STORAGE_BUCKET_NAME')

# Django file storage
DEFAULT_FILE_STORAGE = 'apps.storage.backends.VendorNeutralStorage'
MEDIA_URL = f"https://{DEFAULT_FILE_STORAGE_BUCKET}.s3.{AWS_S3_REGION_NAME}.amazonaws.com/"

# Redis settings
REDIS_URL = environ_setting('REDIS_URL')

# Cache settings
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': REDIS_URL,
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        }
    }
}