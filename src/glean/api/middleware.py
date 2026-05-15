"""API middleware for HTTP hardening."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
        response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
        return response


class LimitBodySizeMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, max_bytes: int = 1_048_576) -> None:
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > self.max_bytes:
                    return JSONResponse({"detail": "request too large"}, status_code=413)
            except ValueError:
                # Malformed Content-Length header; fall through to streaming
                # cap below which enforces the limit independently.
                pass

        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > self.max_bytes:
                return JSONResponse({"detail": "request too large"}, status_code=413)
            body.extend(chunk)
        request._body = bytes(body)
        return await call_next(request)
