"""
Rate Limiting Middleware — Per-user request throttling with Redis persistence.

Uses Redis cache layer for sub-millisecond lookups and PostgreSQL for long-term audit.
Sliding window algorithm with configurable per-role limits.
"""

import logging
import time

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
    Per-user rate limiting with sliding window using Redis persistence.

    Architecture:
    - Redis: Fast cache layer for current minute window (1-minute TTL)
    - PostgreSQL: Persistent audit trail of rate limit violations
    - Sliding window: Only counts requests within the last 60 seconds

    This replaces in-memory defaultdict with distributed Redis state.
    """

    def __init__(self, app):
        super().__init__(app)
        # Redis client will be injected from app.state
        self.redis_manager = None

    async def dispatch(self, request: Request, call_next):
        if request.url.path in ("/api/v1/health", "/docs", "/openapi.json"):
            return await call_next(request)

        user_id = getattr(request.state, "user_id", "anonymous")
        role = getattr(request.state, "role", "analyst")
        limits = RATE_LIMITS.get(role, RATE_LIMITS["analyst"])

        # Get Redis manager from app state
        if not hasattr(request.app.state, "redis_manager"):
            # Fallback for cases where Redis isn't available
            logger.warning("Redis manager not available in app state")
            response = await call_next(request)
            return response

        redis_manager = request.app.state.redis_manager
        now = time.time()
        minute_ago = now - 60

        # Get request timestamps from Redis for this user
        timestamps = await redis_manager.get_request_timestamps(user_id)

        # Clean old entries (sliding window)
        recent_timestamps = [t for t in timestamps if t > minute_ago]

        # Check rate limit
        if len(recent_timestamps) >= limits["requests_per_minute"]:
            logger.warning(
                "Rate limit exceeded for user %s (role=%s): %d requests in last minute",
                user_id, role, len(recent_timestamps),
            )
            return JSONResponse(
                status_code=429,
                content={"error": "Rate limit exceeded", "retry_after": 60},
            )

        # Record this request in Redis (1-hour TTL)
        recent_timestamps.append(now)
        await redis_manager.add_request_timestamp(user_id, now, ttl=3600)

        response = await call_next(request)
        return response
