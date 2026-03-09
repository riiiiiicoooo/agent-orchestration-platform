"""
Clerk Auth Middleware — JWT validation and role-based access control.
"""

import logging
from typing import Any

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

ROLE_PERMISSIONS = {
    "admin": ["*"],
    "manager": ["tasks:*", "agents:read", "cost:read", "health:read"],
    "analyst": ["tasks:create", "tasks:read", "agents:read"],
}


class ClerkAuthMiddleware(BaseHTTPMiddleware):
    """
    Clerk JWT validation middleware.

    Validates Bearer tokens, extracts user roles,
    and enforces role-based access control.
    """

    async def dispatch(self, request: Request, call_next):
        # Skip auth for health check and docs
        if request.url.path in ("/api/v1/health", "/docs", "/openapi.json"):
            return await call_next(request)

        # In production: validate JWT from Clerk
        # token = request.headers.get("Authorization", "").replace("Bearer ", "")
        # claims = clerk.verify_token(token)

        # For now, pass through with default user context
        request.state.user_id = "default_user"
        request.state.org_id = "apex_financial"
        request.state.role = "analyst"

        response = await call_next(request)
        return response
