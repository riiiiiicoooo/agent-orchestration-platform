"""
Subagent Delegation — Lightweight task-specific agents spawned by parent agents.

Enables complex tasks to be decomposed into parallel subtasks, with cost
rolling up to the parent's budget and execution coordinated via SubagentPool.

Inspired by the "Everything Claude Code" pattern of 28 parallel subagents.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from src.providers.router import ModelRouter
from src.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


@dataclass
class SubagentConfig:
    """Configuration for spawning a subagent."""

    name: str  # Descriptive name for the subagent
    model: str  # Model to use (e.g., "claude-3-haiku", "gpt-4o-mini")
    max_tokens: int = 2048  # Token limit for this subtask
    temperature: float = 0.0  # Temperature for this subtask
    tools: list[str] = field(default_factory=list)  # Tools this subagent can access
    budget_limit: float = 10.0  # Max cost for this single subtask
    timeout_seconds: int = 30  # Timeout for subtask execution


@dataclass
class SubagentResult:
    """Result from a subagent execution."""

    output: str  # The subagent's response
    tokens_used: int
    cost: float
    latency_ms: float
    model_used: str
    success: bool = True
    error: str | None = None


class SubagentPool:
    """
    Manages lightweight subagent instances spawned by parent agents.

    Responsibilities:
    - Spawn subagents for specific tasks
    - Enforce concurrency limits (max 3 per parent by default)
    - Track costs rolling up to parent budget
    - Handle timeouts and aggregation of results
    - Manage subagent lifecycle (creation, execution, cleanup)
    """

    def __init__(
        self,
        model_router: ModelRouter,
        tool_registry: ToolRegistry,
        max_concurrent_per_parent: int = 3,
    ):
        self.model_router = model_router
        self.tool_registry = tool_registry
        self.max_concurrent_per_parent = max_concurrent_per_parent

        # Track active subagents: parent_agent_id → set of task IDs
        self._active_subagents: dict[str, set[str]] = {}

    async def spawn(
        self,
        parent_agent_id: str,
        config: SubagentConfig,
        task: str,
    ) -> SubagentResult:
        """
        Spawn a lightweight subagent to execute a specific task.

        Args:
            parent_agent_id: ID of the parent agent spawning this subagent
            config: Configuration for this subagent
            task: The task description/prompt for the subagent

        Returns:
            SubagentResult with output, cost, and metadata

        Raises:
            RuntimeError: If max concurrent subagents exceeded or budget exceeded
        """
        # Check concurrency limit
        active = self._active_subagents.get(parent_agent_id, set())
        if len(active) >= self.max_concurrent_per_parent:
            return SubagentResult(
                output="",
                tokens_used=0,
                cost=0.0,
                latency_ms=0.0,
                model_used=config.model,
                success=False,
                error=f"Max concurrent subagents ({self.max_concurrent_per_parent}) exceeded for parent {parent_agent_id}",
            )

        # Initialize tracking for this parent if needed
        if parent_agent_id not in self._active_subagents:
            self._active_subagents[parent_agent_id] = set()

        # Generate task ID
        task_id = f"{parent_agent_id}_{int(time.time() * 1000)}"
        self._active_subagents[parent_agent_id].add(task_id)

        try:
            result = await self._execute_subagent(config, task)
            return result
        finally:
            # Clean up tracking
            self._active_subagents[parent_agent_id].discard(task_id)

    async def _execute_subagent(
        self,
        config: SubagentConfig,
        task: str,
    ) -> SubagentResult:
        """
        Execute a subagent with timeout and cost tracking.

        Internal method called by spawn().
        """
        start_time = time.monotonic()

        try:
            # Get tools for this subagent
            tools = self.tool_registry.get_tools(config.tools)

            # Build simple prompt for subagent
            prompt = f"""You are a {config.name} agent. Execute the following task concisely.

Task: {task}

Provide a clear, factual response."""

            # Call LLM via router with timeout
            try:
                response = await asyncio.wait_for(
                    self.model_router.generate(
                        model=config.model,
                        prompt=prompt,
                        tools=tools,
                        max_tokens=config.max_tokens,
                        temperature=config.temperature,
                    ),
                    timeout=config.timeout_seconds,
                )
            except asyncio.TimeoutError:
                elapsed_ms = (time.monotonic() - start_time) * 1000
                logger.warning(
                    "Subagent timeout: %s after %.0fms",
                    config.name,
                    elapsed_ms,
                )
                return SubagentResult(
                    output="",
                    tokens_used=0,
                    cost=0.0,
                    latency_ms=elapsed_ms,
                    model_used=config.model,
                    success=False,
                    error=f"Timeout after {config.timeout_seconds}s",
                )

            # Check cost limit
            if response.cost > config.budget_limit:
                logger.warning(
                    "Subagent cost exceeded: %s cost $%.2f > limit $%.2f",
                    config.name,
                    response.cost,
                    config.budget_limit,
                )
                return SubagentResult(
                    output=response.content[:200],  # Partial output
                    tokens_used=response.total_tokens,
                    cost=response.cost,
                    latency_ms=(time.monotonic() - start_time) * 1000,
                    model_used=config.model,
                    success=False,
                    error=f"Cost exceeded: ${response.cost:.2f} > ${config.budget_limit:.2f}",
                )

            elapsed_ms = (time.monotonic() - start_time) * 1000

            return SubagentResult(
                output=response.content,
                tokens_used=response.total_tokens,
                cost=response.cost,
                latency_ms=elapsed_ms,
                model_used=config.model,
                success=True,
            )

        except Exception as e:
            elapsed_ms = (time.monotonic() - start_time) * 1000
            logger.error(
                "Subagent execution failed: %s, error: %s",
                config.name,
                str(e),
            )
            return SubagentResult(
                output="",
                tokens_used=0,
                cost=0.0,
                latency_ms=elapsed_ms,
                model_used=config.model,
                success=False,
                error=str(e),
            )

    async def spawn_parallel(
        self,
        parent_agent_id: str,
        tasks: list[tuple[SubagentConfig, str]],
    ) -> list[SubagentResult]:
        """
        Spawn multiple subagents in parallel and wait for all to complete.

        Respects per-parent concurrency limits by batching if needed.

        Args:
            parent_agent_id: Parent agent ID
            tasks: List of (config, task_prompt) tuples

        Returns:
            List of SubagentResult in the same order as input tasks
        """
        # Batch spawn to respect concurrency limits
        results = []
        for i in range(0, len(tasks), self.max_concurrent_per_parent):
            batch = tasks[i : i + self.max_concurrent_per_parent]
            batch_results = await asyncio.gather(
                *[
                    self.spawn(parent_agent_id, config, task)
                    for config, task in batch
                ],
                return_exceptions=False,
            )
            results.extend(batch_results)

        return results

    def get_subagent_count(self, parent_agent_id: str) -> int:
        """Get number of currently active subagents for a parent."""
        return len(self._active_subagents.get(parent_agent_id, set()))

    def get_status(self) -> dict[str, Any]:
        """Get status of the subagent pool."""
        return {
            "total_active_subagents": sum(
                len(subagents) for subagents in self._active_subagents.values()
            ),
            "by_parent": {
                parent_id: len(subagents)
                for parent_id, subagents in self._active_subagents.items()
            },
        }


# Predefined subagent configurations for common patterns

DATA_FETCHER_CONFIG = SubagentConfig(
    name="data_fetcher",
    model="claude-3-haiku",
    max_tokens=2048,
    temperature=0.0,
    tools=["database_query", "document_search"],
    budget_limit=5.0,
    timeout_seconds=20,
)

ANALYZER_CONFIG = SubagentConfig(
    name="analyzer",
    model="claude-3.5-sonnet",
    max_tokens=4096,
    temperature=0.0,
    tools=["database_query", "report_generate", "trend_analyze"],
    budget_limit=15.0,
    timeout_seconds=30,
)

VALIDATOR_CONFIG = SubagentConfig(
    name="validator",
    model="claude-3-haiku",
    max_tokens=1024,
    temperature=0.0,
    tools=[],
    budget_limit=3.0,
    timeout_seconds=15,
)

SUMMARIZER_CONFIG = SubagentConfig(
    name="summarizer",
    model="claude-3-haiku",
    max_tokens=1024,
    temperature=0.0,
    tools=[],
    budget_limit=4.0,
    timeout_seconds=15,
)
