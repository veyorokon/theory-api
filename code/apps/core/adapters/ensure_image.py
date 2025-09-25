# Compatibility shim for ensure_image module
# Image validation now handled by build/pin pipeline in HTTP-first architecture


def ensure_image_pinned(*args, **kwargs):
    """Legacy image validation - handled by build/pin pipeline now"""
    raise NotImplementedError("Image pinning handled by build/pin pipeline")
