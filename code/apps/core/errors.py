"""
Canonical error codes for Theory Runtime.

These error codes provide a stable interface for clients and are used
consistently across all adapters and components.
"""

# Image and registry errors
ERR_IMAGE_UNPINNED = "ERR_IMAGE_UNPINNED"

# Secret and authentication errors  
ERR_MISSING_SECRET = "ERR_MISSING_SECRET"

# Path validation errors
ERR_DECODED_SLASH = "ERR_DECODED_SLASH"
ERR_DOT_SEGMENTS = "ERR_DOT_SEGMENTS"

# Template and prefix errors
ERR_PREFIX_TEMPLATE = "ERR_PREFIX_TEMPLATE"

# Output handling errors
ERR_OUTPUT_DUPLICATE = "ERR_OUTPUT_DUPLICATE"

# Adapter execution errors
ERR_ADAPTER_INVOCATION = "ERR_ADAPTER_INVOCATION"