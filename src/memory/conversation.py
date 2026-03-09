"""
Conversation Memory (Layer 2) — PostgreSQL-backed conversation history.

Stores full interaction history with metadata for audit trails,
analytics, and context retrieval. 90-day retention with archival.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from langsmith import traceable

logger = logging.getLogger(__name__)


class ConversationStore:
    """
    PostgreSQL-backed conversation history.

    Layer 2 of three-tier memory architecture.
    Stores complete interaction records with agent attribution,
    cost tracking, and quality metadata.
    """

    def __init__(self, database_url: str):
        self.database_url = database_url
        self.pool = None  # asyncpg connection pool

    async def connect(self) -> None:
        """Initialize database connection pool."""
        # In production: asyncpg.create_pool(self.database_url)
        logger.info("Conversation store connected")

    async def append(
        self,
        session_id: str,
        user_input: str,
        response: str,
        intent: Any = None,
        agents_used: list[str] | None = None,
        latency_ms: int = 0,
        token_usage: int = 0,
        cost: float = 0.0,
    ) -> None:
        """
        Append a conversation turn to history.

        Stores both the interaction and metadata for downstream analytics.
        """
        record = {
            "session_id": session_id,
            "user_input": user_input,
            "response": response,
            "intent_domain": intent.domain if intent else None,
            "intent_complexity": intent.complexity if intent else None,
            "agents_used": agents_used or [],
            "latency_ms": latency_ms,
            "token_usage": token_usage,
            "cost": cost,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        # In production: INSERT INTO conversations (...)
        logger.debug(
            "Conversation appended: session=%s, agents=%s, cost=$%.4f",
            session_id, agents_used, cost,
        )

    async def get_recent(
        self,
        session_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Retrieve recent conversation turns for context."""
        # In production: SELECT * FROM conversations WHERE session_id = $1 ORDER BY created_at DESC LIMIT $2
        return []

    async def get_session_summary(self, session_id: str) -> dict[str, Any]:
        """Get aggregated session metrics."""
        # In production: Aggregation query
        return {
            "session_id": session_id,
            "total_turns": 0,
            "total_tokens": 0,
            "total_cost": 0.0,
            "agents_used": [],
            "duration_seconds": 0,
        }

    @traceable(name="conversation_store.search_history")
    async def search_history(
        self,
        query: str,
        user_id: str | None = None,
        date_range: tuple[str, str] | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Full-text search across conversation history."""
        # In production: PostgreSQL full-text search with ts_vector
        return []
