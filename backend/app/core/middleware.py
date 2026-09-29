"""ASGI middlewares: request-id, access logging, security headers.

The chain is deliberately small and composes with FastAPI's middleware stack
(CORS, trusted hosts) installed in :mod:`app.main`.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings

logger = structlog.get_logger("http.access")


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a request id (honours incoming ``X-Request-ID``) and basic timing."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        started = time.perf_counter()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000

        response.headers["X-Request-ID"] = request_id
        if settings.request_logging:
            logger.info(
                "request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration_ms=round(elapsed_ms, 1),
                client_ip=request.client.host if request.client else None,
                slow=elapsed_ms > settings.slow_request_ms,
            )
        structlog.contextvars.unbind_contextvars("request_id")
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add baseline hardening headers to every response."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        response = await call_next(request)
        headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
            "X-XSS-Protection": "0",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=(self)",
            "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
            "Cache-Control": "no-store",
        }
        for k, v in headers.items():
            response.headers.setdefault(k, v)
        return response


__all__ = ["RequestIdMiddleware", "SecurityHeadersMiddleware"]
