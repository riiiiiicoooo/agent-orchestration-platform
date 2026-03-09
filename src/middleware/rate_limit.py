"""
Rate Limiting Middleware — Per-user request throttling.
"""

import logging
import time
from collections import defaultdict

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# Rate limits per role
RATE_LIMITS = {
    "admin": {"requests_per_minute": 120, "requests_per_hour": 3000},
    "manager": {"requests_per_minute": 60, "requests_per_hour": 1500},
    "analyst": {"requests_per_minute": 30, "requests_per_hour": 500},
}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Per-user rate limiting with sliding window.

    Uses in-memory counters (Redis in production for multi-instance).
    """

    def __init__(self, app):
        super().__init__(app)
        self.request_counts: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        if request.url.path in ("/api/v1/health", "/docs", "/openapi.json"):
            return await call_next(request)

        user_id = getattr(request.state, "user_id", "anonymous")
        role = getattr(request.state, "role", "analyst")
        limits = RATE_LIMITS.get(role, RATE_LIMITS["analyst"])

        now = time.time()
        minute_ago = now - 60

        # Clean old entries
        self.request_counts[user_id] = [
            t for t in self.request_counts[user_id] if t > minute_ago
        ]

        if len(self.request_counts[user_id]) >= limits["requests_per_minute"]:
            return JSONResponse(
                status_code=429,
                content={"error": "Rate limit exceeded", "retry_after": 60},
            )

        self.request_counts[user_id].append(now)
        response = await call_next(request)
        return response
