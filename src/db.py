"""
Database Layer — SQLAlchemy ORM with connection pooling and Redis client.

Provides persistent storage for:
- Rate limiting state (request timestamps per user)
- Cost tracking (per-model, per-provider, total)
- Budget enforcement (agent and user budgets)
- Agent metrics (latencies, task counts, errors)

Connection pooling strategy:
- QueuePool for PostgreSQL (default, handles concurrent connections)
- Redis for fast cache layer (rate limits, cost tracking)
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    Column,
    String,
    Float,
    Integer,
    DateTime,
    JSON,
    create_engine,
    select,
    func,
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import QueuePool
import redis.asyncio as redis

logger = logging.getLogger(__name__)

Base = declarative_base()


class RateLimitRecord(Base):
    """Rate limit tracking per user with sliding window."""
    __tablename__ = "rate_limits"

    id = Column(Integer, primary_key=True)
    user_id = Column(String(256), index=True, nullable=False)
    request_timestamp = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.now(timezone.utc))


class CostRecord(Base):
    """Cost tracking per model and provider."""
    __tablename__ = "cost_records"

    id = Column(Integer, primary_key=True)
    model_name = Column(String(256), index=True, nullable=False)
    provider_name = Column(String(256), index=True, nullable=False)
    cost = Column(Float, nullable=False)
    tokens = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.now(timezone.utc), index=True)


class BudgetRecord(Base):
    """Budget configuration and state for agents and users."""
    __tablename__ = "budgets"

    id = Column(Integer, primary_key=True)
    entity_id = Column(String(256), unique=True, index=True, nullable=False)
    entity_type = Column(String(50), nullable=False)  # 'agent' or 'user'
    config = Column(JSON, nullable=False)  # BudgetConfig as JSON
    spent_today = Column(Float, nullable=False, default=0.0)
    requests_today = Column(Integer, nullable=False, default=0)
    last_reset = Column(DateTime, nullable=True)
    alerts_sent = Column(JSON, nullable=False, default_factory=list)
    created_at = Column(DateTime, default=datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))


class AgentMetricRecord(Base):
    """Agent performance metrics (latencies, errors, task counts)."""
    __tablename__ = "agent_metrics"

    id = Column(Integer, primary_key=True)
    agent_id = Column(String(256), index=True, nullable=False)
    latencies = Column(JSON, nullable=False, default_factory=list)  # Last 100 latencies
    tasks_completed_today = Column(Integer, nullable=False, default=0)
    budget_used_today = Column(Float, nullable=False, default=0.0)
    errors_today = Column(Integer, nullable=False, default=0)
    circuit_breaker_state = Column(String(50), nullable=False, default="closed")
    circuit_breaker_failure_count = Column(Integer, nullable=False, default=0)
    circuit_breaker_last_failure = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime, default=datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))


class DatabaseManager:
    """
    Manages async SQLAlchemy connections with QueuePool for connection pooling.

    QueuePool benefits:
    - Handles concurrent requests efficiently
    - Configurable queue size and overflow behavior
    - Automatic connection recycling
    - Thread-safe and async-compatible
    """

    def __init__(self, database_url: str):
        self.database_url = database_url
        self.engine = None
        self.async_session = None

    async def initialize(self) -> None:
        """Create async engine with QueuePool connection pooling."""
        self.engine = create_async_engine(
            self.database_url,
            echo=False,
            poolclass=QueuePool,
            pool_size=20,  # Number of connections to keep in pool
            max_overflow=40,  # Additional connections allowed beyond pool_size
            pool_recycle=3600,  # Recycle connections every hour
            pool_pre_ping=True,  # Verify connections before using them
            connect_args={
                "timeout": 10,
                "server_settings": {
                    "application_name": "agent_orchestration_platform",
                },
            },
        )

        self.async_session = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        # Create tables
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        logger.info("Database initialized with QueuePool (%d size, %d overflow)", 20, 40)

    async def get_session(self) -> AsyncSession:
        """Get a new async database session."""
        if not self.async_session:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        return self.async_session()

    async def close(self) -> None:
        """Close all connections."""
        if self.engine:
            await self.engine.dispose()


class RedisManager:
    """
    Redis client wrapper for fast cache layer.

    Caches:
    - Rate limit request timestamps (sliding window)
    - Cost totals (updated in real-time)
    - Budget state (spent_today, requests_today)
    - Agent metrics snapshots
    """

    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self.client = None

    async def initialize(self) -> None:
        """Connect to Redis."""
        self.client = redis.from_url(self.redis_url, decode_responses=True)
        await self.client.ping()
        logger.info("Redis client connected: %s", self.redis_url)

    async def close(self) -> None:
        """Close Redis connection."""
        if self.client:
            await self.client.close()

    async def get_request_timestamps(self, user_id: str) -> list[float]:
        """Get recent request timestamps for rate limiting."""
        data = await self.client.get(f"rate_limit:{user_id}")
        if data:
            return json.loads(data)
        return []

    async def add_request_timestamp(self, user_id: str, timestamp: float, ttl: int = 3600) -> None:
        """Add a request timestamp for sliding window rate limiting."""
        timestamps = await self.get_request_timestamps(user_id)
        timestamps.append(timestamp)
        await self.client.setex(
            f"rate_limit:{user_id}",
            ttl,
            json.dumps(timestamps),
        )

    async def get_cost_summary(self) -> dict[str, Any]:
        """Get cached cost summary."""
        total_cost_str = await self.client.get("cost:total")
        by_model_str = await self.client.get("cost:by_model")
        by_provider_str = await self.client.get("cost:by_provider")

        return {
            "total_cost": float(total_cost_str or 0),
            "by_model": json.loads(by_model_str) if by_model_str else {},
            "by_provider": json.loads(by_provider_str) if by_provider_str else {},
        }

    async def set_cost_summary(self, summary: dict[str, Any], ttl: int = 86400) -> None:
        """Cache cost summary."""
        await self.client.setex("cost:total", ttl, str(summary.get("total_cost", 0)))
        await self.client.setex(
            "cost:by_model",
            ttl,
            json.dumps(summary.get("by_model", {})),
        )
        await self.client.setex(
            "cost:by_provider",
            ttl,
            json.dumps(summary.get("by_provider", {})),
        )

    async def increment_cost(
        self,
        model: str,
        provider: str,
        cost: float,
        ttl: int = 86400,
    ) -> None:
        """Increment cost for a model and provider."""
        # Update total cost
        current_total = float(await self.client.get("cost:total") or 0)
        await self.client.setex("cost:total", ttl, str(current_total + cost))

        # Update by-model cost
        by_model = json.loads(await self.client.get("cost:by_model") or "{}")
        by_model[model] = by_model.get(model, 0.0) + cost
        await self.client.setex("cost:by_model", ttl, json.dumps(by_model))

        # Update by-provider cost
        by_provider = json.loads(await self.client.get("cost:by_provider") or "{}")
        by_provider[provider] = by_provider.get(provider, 0.0) + cost
        await self.client.setex("cost:by_provider", ttl, json.dumps(by_provider))

    async def get_budget_state(self, entity_id: str) -> dict[str, Any]:
        """Get cached budget state."""
        data = await self.client.get(f"budget:{entity_id}")
        if data:
            return json.loads(data)
        return {
            "spent_today": 0.0,
            "requests_today": 0,
            "alerts_sent": [],
        }

    async def set_budget_state(self, entity_id: str, state: dict[str, Any], ttl: int = 86400) -> None:
        """Cache budget state."""
        await self.client.setex(
            f"budget:{entity_id}",
            ttl,
            json.dumps(state),
        )

    async def delete_expired_keys(self, pattern: str) -> int:
        """Delete expired keys matching a pattern."""
        keys = await self.client.keys(pattern)
        if keys:
            return await self.client.delete(*keys)
        return 0


# Pagination utilities for unbounded list endpoints
class PaginationParams:
    """Query parameters for paginated list endpoints."""

    def __init__(self, skip: int = 0, limit: int = 20):
        self.skip = max(0, skip)
        self.limit = min(limit, 100)  # Cap at 100 per page

    def to_sql(self) -> tuple[int, int]:
        """Return (offset, limit) for SQL queries."""
        return (self.skip, self.limit)


async def get_paginated_results(
    session: AsyncSession,
    query,
    skip: int = 0,
    limit: int = 20,
) -> tuple[list, int]:
    """
    Execute a paginated query.

    Returns:
        (results, total_count)
    """
    # Get total count
    count_query = select(func.count()).select_from(query.froms[0])
    total = await session.scalar(count_query)

    # Get paginated results
    paginated_query = query.offset(skip).limit(limit)
    results = await session.execute(paginated_query)

    return results.scalars().all(), total or 0
