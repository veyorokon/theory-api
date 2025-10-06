from .dev_local import *

# Override storage to use S3 for Modal compatibility
STORAGE_BACKEND = "s3"
ARTIFACTS_BUCKET = env("ARTIFACTS_BUCKET")
ARTIFACTS_REGION = env("ARTIFACTS_REGION")

STORAGE = {
    "BACKEND": "s3",
    "BUCKET": ARTIFACTS_BUCKET,
    "REGION": ARTIFACTS_REGION,
}
