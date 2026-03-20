"""
Memory Consolidation — Compresses long sessions into reusable knowledge.

Implements the "compaction" pattern for memory efficiency:
- Summarize long sessions into key facts
- Archive old conversations to cold storage
- Find similar sessions via semantic search
- Extract recurring patterns for organizational learning
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SessionSummary:
    """Compressed representation of a session."""

    session_id: str
    user_id: str
    duration_seconds: int
    key_facts: list[str]  # Extracted key facts/decisions
    agents_used: list[str]  # Which agents were invoked
    domains_covered: list[str]  # Problem domains addressed
    total_tokens: int
    total_cost: float
    created_at: datetime
    summarized_at: datetime | None = None


@dataclass
class PatternInsight:
    """A recurring pattern identified across sessions."""

    pattern_id: str
    description: str  # Human-readable description
    frequency: int  # How many sessions exhibited this pattern
    example_sessions: list[str]  # Sample session IDs
    recommendation: str  # Action to take based on this pattern


class MemoryConsolidator:
    """
    Manages memory consolidation, archival, and pattern extraction.

    Enables agents to learn from history and avoid recomputing
    similar analyses by compressing long-term memory.
    """

    def __init__(
        self,
        db_manager=None,
        session_store=None,
        knowledge_store=None,
    ):
        self.db_manager = db_manager
        self.session_store = session_store
        self.knowledge_store = knowledge_store

    async def consolidate_session(
        self,
        session_id: str,
        min_messages: int = 5,
    ) -> SessionSummary | None:
        """
        Summarize a long session into key facts for efficient storage.

        Extracts:
        - Key decisions made
        - Problems solved
        - Agents involved
        - Resource usage

        Args:
            session_id: Session to consolidate
            min_messages: Minimum messages before consolidation worthwhile

        Returns:
            SessionSummary or None if session too short
        """
        # In production: retrieve session from conversation store
        logger.info("Consolidating session %s", session_id)

        # Would retrieve actual conversation history here
        conversation = await self._get_conversation(session_id)

        if len(conversation) < min_messages:
            logger.debug(
                "Session %s too short for consolidation (%d messages)",
                session_id,
                len(conversation),
            )
            return None

        # Extract key facts via LLM summarization
        key_facts = await self._extract_key_facts(conversation)

        # Extract metadata
        agents_used = await self._extract_agents(conversation)
        domains = await self._extract_domains(conversation)
        tokens = sum(msg.get("tokens", 0) for msg in conversation)
        cost = sum(msg.get("cost", 0.0) for msg in conversation)

        # Calculate duration
        start_time = conversation[0].get("timestamp", datetime.now())
        end_time = conversation[-1].get("timestamp", datetime.now())
        duration = (end_time - start_time).total_seconds()

        summary = SessionSummary(
            session_id=session_id,
            user_id=conversation[0].get("user_id", "unknown"),
            duration_seconds=int(duration),
            key_facts=key_facts,
            agents_used=agents_used,
            domains_covered=domains,
            total_tokens=tokens,
            total_cost=cost,
            created_at=start_time,
            summarized_at=datetime.now(),
        )

        # Store summary in database
        await self._store_summary(summary)

        logger.info(
            "Consolidated session %s: %d facts, agents=%s, cost=$%.2f",
            session_id,
            len(key_facts),
            agents_used,
            cost,
        )

        return summary

    async def archive_old_conversations(
        self,
        days: int = 90,
        batch_size: int = 100,
    ) -> int:
        """
        Move conversations older than N days to cold storage.

        In production: moves from hot PostgreSQL to S3 or archive table
        for cost efficiency while maintaining queryability.

        Args:
            days: Age threshold (default 90 days)
            batch_size: Process in batches to avoid locking

        Returns:
            Number of conversations archived
        """
        logger.info("Archiving conversations older than %d days", days)

        cutoff_date = datetime.now() - timedelta(days=days)
        archived_count = 0

        # In production: would query conversation store for old records
        # and move them to cold storage (S3 + metadata in separate table)

        logger.info("Archived %d conversations", archived_count)
        return archived_count

    async def find_similar_sessions(
        self,
        query: str,
        limit: int = 5,
        similarity_threshold: float = 0.7,
    ) -> list[SessionSummary]:
        """
        Find semantically similar sessions via embedding search.

        Allows agents to reference how similar problems were solved before.

        Args:
            query: Search query (user intent or problem description)
            limit: Max results to return
            similarity_threshold: Minimum similarity score

        Returns:
            List of similar SessionSummary objects
        """
        logger.info("Searching for sessions similar to: %s", query)

        # In production: generate embedding for query, search pgvector
        # against session summary embeddings

        # Stub: return empty
        return []

    async def extract_patterns(
        self,
        session_ids: list[str] | None = None,
        sample_size: int = 100,
    ) -> list[PatternInsight]:
        """
        Analyze sessions to identify recurring patterns.

        Useful for:
        - Identifying common failure modes
        - Discovering agent capacity bottlenecks
        - Finding cost optimization opportunities
        - Recommending workflow improvements

        Args:
            session_ids: Specific sessions to analyze (all if None)
            sample_size: Max sessions to analyze (if None provided)

        Returns:
            List of PatternInsight objects
        """
        logger.info(
            "Extracting patterns from %d sessions",
            len(session_ids) if session_ids else sample_size,
        )

        # In production: would analyze session metadata and conversation
        # patterns to identify:
        # - Agent failure modes
        # - Cost spikes
        # - Latency bottlenecks
        # - Escalation triggers

        patterns: list[PatternInsight] = []

        # Example pattern (stub)
        patterns.append(
            PatternInsight(
                pattern_id="high_cost_document_processing",
                description="Document processing agent exceeds budget on multi-page PDFs",
                frequency=15,
                example_sessions=[],
                recommendation="Implement document chunking before agent invocation",
            )
        )

        logger.info("Extracted %d patterns", len(patterns))
        return patterns

    async def get_consolidation_stats(self) -> dict[str, Any]:
        """Get statistics on memory consolidation."""
        # In production: query database for consolidation metrics
        return {
            "total_sessions": 0,
            "consolidated_sessions": 0,
            "archived_conversations": 0,
            "storage_saved_bytes": 0,
        }

    # Private helpers

    async def _get_conversation(self, session_id: str) -> list[dict]:
        """Retrieve conversation history for a session."""
        if not self.session_store:
            return []
        # Would retrieve from conversation store
        return []

    async def _extract_key_facts(self, conversation: list[dict]) -> list[str]:
        """Extract key facts/decisions from conversation."""
        # In production: use Claude to summarize
        # For now: simple extraction
        facts = []
        for msg in conversation:
            if msg.get("role") == "assistant" and len(msg.get("content", "")) > 100:
                # Simple heuristic: take first 200 chars of long responses
                facts.append(msg.get("content", "")[:200])
        return facts[:10]  # Keep top 10

    async def _extract_agents(self, conversation: list[dict]) -> list[str]:
        """Extract which agents were used."""
        agents = set()
        for msg in conversation:
            if agent_id := msg.get("agent_id"):
                agents.add(agent_id)
        return list(agents)

    async def _extract_domains(self, conversation: list[dict]) -> list[str]:
        """Extract problem domains covered."""
        domains = set()
        for msg in conversation:
            if domain := msg.get("domain"):
                domains.add(domain)
        return list(domains)

    async def _store_summary(self, summary: SessionSummary) -> None:
        """Store session summary in database."""
        if not self.db_manager:
            return

        # In production: would insert into session_summary table
        logger.debug("Stored summary for session %s", summary.session_id)
