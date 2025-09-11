# apps/core/utils/mime.py
from __future__ import annotations
import mimetypes

def guess_mime(path: str) -> str:
    mime, _ = mimetypes.guess_type(path, strict=False)
    return mime or "application/octet-stream"
