from .dev_local import *

# Override storage to use S3 for Modal compatibility
STORAGE_BACKEND = "s3"
ARTIFACTS_BUCKET = env("ARTIFACTS_BUCKET", required=True)
ARTIFACTS_REGION = env("ARTIFACTS_REGION", required=True)

STORAGE = {
    "BACKEND": "s3",
    "BUCKET": ARTIFACTS_BUCKET,
    "REGION": ARTIFACTS_REGION,
}
