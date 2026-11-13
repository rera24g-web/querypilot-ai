"""CSRF protection middleware."""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse
from starlette.status import HTTP_403_FORBIDDEN
import logging

logger = logging.getLogger(__name__)

# Endpoints that require CSRF protection (state-changing operations)
CSRF_PROTECTED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
# Endpoints to exclude from CSRF protection
CSRF_EXEMPT_PATHS = {
    "/api/health",
    "/api/schema",
    "/auth/register",
    "/auth/login",
    "/auth/logout",
    "/auth/me",
    "/docs",
    "/redoc",
    "/openapi.json",
}


class CSRFMiddleware(BaseHTTPMiddleware):
    """Middleware for CSRF protection using double-submit cookie pattern.

    Security contract:
    - For authenticated endpoints: CSRF is checked only if session exists
    - Unauthenticated requests (no session_id cookie) fail at auth layer with 401
    - Authenticated requests must provide valid CSRF token (both cookie and header match)
    - This preserves fail-closed CSRF validation while providing proper 401 for unauthenticated requests
    """

    async def dispatch(self, request: Request, call_next):
        # Skip CSRF for exempt paths
        if request.url.path in CSRF_EXEMPT_PATHS:
            return await call_next(request)

        # Skip CSRF for safe methods
        if request.method not in CSRF_PROTECTED_METHODS:
            return await call_next(request)

        # Skip for paths that start with /api/investigations but are GET
        if request.url.path.startswith("/api/investigations") and request.method == "GET":
            return await call_next(request)

        # Get session cookie
        session_id = request.cookies.get("session_id")

        # Get CSRF token from cookie and header
        csrf_cookie = request.cookies.get("csrf_token")
        csrf_header = request.headers.get("X-CSRF-Token") or request.headers.get("X-XSRF-Token")

        # If no session cookie, let auth handle 401 (session required for authenticated endpoints)
        # This ensures POST requests without any session get 401 instead of 403 (CSRF blocked)
        if not session_id:
            return await call_next(request)

        # At this point, we have a session - CSRF token must also be present
        # Validate CSRF token
        if not csrf_cookie or not csrf_header:
            logger.warning(f"CSRF validation failed: missing token for {request.url.path}")
            return JSONResponse(
                status_code=HTTP_403_FORBIDDEN,
                content={"detail": "CSRF token missing"}
            )

        # Simple string comparison (tokens are cryptographically random)
        if csrf_cookie != csrf_header:
            logger.warning(f"CSRF validation failed: token mismatch for {request.url.path}")
            return JSONResponse(
                status_code=HTTP_403_FORBIDDEN,
                content={"detail": "CSRF token invalid"}
            )

        return await call_next(request)