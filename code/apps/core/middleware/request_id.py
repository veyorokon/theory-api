from __future__ import annotations
import uuid
import time
from django.utils.deprecation import MiddlewareMixin
from apps.core.logging import bind, clear, info


class RequestIdMiddleware(MiddlewareMixin):
    """Request ID middleware for logging context binding."""

    def process_request(self, request):
        """Bind request context and log request start."""
        rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request._rid = rid
        bind(request_id=rid, route=getattr(request, "path", "/"), method=getattr(request, "method", ""))
        info("request.start")

    def process_response(self, request, response):
        """Log request end and clear context."""
        try:
            info("request.end", status_code=getattr(response, "status_code", 0))
        finally:
            clear()
        response["X-Request-ID"] = getattr(request, "_rid", "")
        return response
