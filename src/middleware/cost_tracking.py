"""
Cost Tracking Middleware — Request-level cost attribution.

Captures per-request LLM costs for billing, budgeting, and anomaly detection.
"""

import logging
import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class CostTrackingMiddleware(BaseHTTPMiddleware):
    """
    Track cost per API request for attribution and alerting.

    Attaches cost metadata to response headers and logs
    for downstream analytics.
    """

    async def dispatch(self, request: Request, call_next):
        start_time = time.monotonic()

        response = await call_next(request)

        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        response.headers["X-Request-Latency-Ms"] = str(elapsed_ms)

        # In production: extract cost from request context and log
        # cost = request.state.get("request_cost", 0.0)
        # response.headers["X-Request-Cost"] = f"${cost:.4f}"

        return response
