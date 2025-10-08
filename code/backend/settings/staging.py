from .dev_remote import *

# Staging uses S3 (inherited from dev_remote)
# Override environment designation
MODAL_ENVIRONMENT = env("MODAL_ENVIRONMENT", default="staging", required=MODAL_ENABLED)
