"""
Session Memory (Layer 1) — Redis-backed fast state for active agent sessions.

Sub-millisecond reads for active context. TTL-based expiration ensures
stale sessions are cleaned up automatically.
"""

import json
import logging
from typing import Any

import redis.asyncio as redis

logger = logging.getLogger(__name__)


class RedisSessionStore:
    """
    Redis-backed session state for active agent conversations.

    Layer 1 of three-tier memory architecture:
    - Redis (this): Sub-ms latency, 30-min TTL, active context
    - PostgreSQL: Conversation history, 90-day retention
    - pgvector: Long-term knowledge, persistent embeddings
    """

    def __init__(self, url: str, default_ttl: int = 1800):
        self.url = url
        self.default_ttl = default_ttl
        self.client: redis.Redis | None = None

    async def connect(self) -> None:
        self.client = redis.from_url(self.url, decode_responses=True)
        await self.client.ping()
        logger.info("Redis session store connected")

    async def disconnect(self) -> None:
        if self.client:
            await self.client.close()

    async def get_context(self, session_id: str) -> dict[str, Any]:
        """Retrieve full session context."""
        if not self.client:
            return {}
        data = await self.client.get(f"session:{session_id}")
        if data:
            return json.loads(data)
        return {}

    async def update_context(self, session_id: str, **kwargs) -> None:
        """Update session context with new data."""
        if not self.client:
            return
        existing = await self.get_context(session_id)
        existing.update(kwargs)
        await self.client.setex(
            f"session:{session_id}",
            self.default_ttl,
            json.dumps(existing),
        )

    async def set_agent_state(
        self,
        session_id: str,
        agent_id: str,
        state: dict[str, Any],
    ) -> None:
        """Store per-agent state within a session."""
        if not self.client:
            return
        await self.client.hset(
            f"session:{session_id}:agents",
            agent_id,
            json.dumps(state),
        )
        await self.client.expire(f"session:{session_id}:agents", self.default_ttl)

    async def get_agent_state(
        self,
        session_id: str,
        agent_id: str,
    ) -> dict[str, Any]:
        """Retrieve per-agent state."""
        if not self.client:
            return {}
        data = await self.client.hget(f"session:{session_id}:agents", agent_id)
        if data:
            return json.loads(data)
        return {}

    async def publish_event(self, channel: str, event: dict[str, Any]) -> None:
        """Publish event to Redis Streams for inter-agent communication."""
        if not self.client:
            return
        await self.client.xadd(
            f"events:{channel}",
            {k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) for k, v in event.items()},
            maxlen=1000,
        )

    async def get_active_sessions(self) -> int:
        """Count active sessions."""
        if not self.client:
            return 0
        keys = await self.client.keys("session:*")
        # Filter out agent sub-keys
        return len([k for k in keys if ":agents" not in k])
