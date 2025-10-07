from .dev_local import *

# Override storage to use S3 for Modal compatibility
STORAGE_BACKEND = "s3"
ARTIFACTS_BUCKET = env("ARTIFACTS_BUCKET", default="theory-artifacts-dev")
ARTIFACTS_REGION = env("ARTIFACTS_REGION", default="us-east-1")

STORAGE = {
    "BACKEND": "s3",
    "BUCKET": ARTIFACTS_BUCKET,
    "REGION": ARTIFACTS_REGION,
}
