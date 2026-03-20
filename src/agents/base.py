"""
Base Agent — Common interface for all specialized agents.

Provides circuit breaker, cost tracking, tool access, and
standardized execution flow that all domain agents inherit.
Integrates with hook system for extensible behavior and supports
subagent spawning for task decomposition.
"""

import logging
import time
from abc import ABC, abstractmethod
from typing import Any

from langsmith import traceable

from src.providers.router import ModelRouter
from src.memory.session import RedisSessionStore
from src.memory.knowledge import KnowledgeStore
from src.tools.registry import ToolRegistry
from src.hooks.engine import HookEngine, HookContext, HookType

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """
    Circuit breaker for agent fault isolation.

    States: closed (normal) → open (failing) → half-open (testing recovery)
    Thresholds tuned per agent criticality.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout_seconds: int = 60,
        half_open_max_calls: int = 3,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout_seconds
        self.half_open_max_calls = half_open_max_calls

        self.state = "closed"
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.half_open_calls = 0

    def record_success(self) -> None:
        if self.state == "half-open":
            self.half_open_calls += 1
            if self.half_open_calls >= self.half_open_max_calls:
                self.state = "closed"
                self.failure_count = 0
                logger.info("Circuit breaker closed — agent recovered")
        elif self.state == "closed":
            self.failure_count = max(0, self.failure_count - 1)

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = time.monotonic()

        if self.failure_count >= self.failure_threshold:
            self.state = "open"
            logger.warning(
                "Circuit breaker OPEN — %d consecutive failures",
                self.failure_count,
            )

    def can_execute(self) -> bool:
        if self.state == "closed":
            return True
        if self.state == "open":
            elapsed = time.monotonic() - self.last_failure_time
            if elapsed >= self.recovery_timeout:
                self.state = "half-open"
                self.half_open_calls = 0
                return True
            return False
        # half-open
        return True


class BaseAgent(ABC):
    """
    Base class for all specialized agents.

    Provides:
    - Standardized execution flow with tracing
    - Circuit breaker for fault isolation
    - Cost tracking per task
    - Tool access via shared registry
    - Retry logic with exponential backoff
    """

    def __init__(
        self,
        agent_id: str,
        model_router: ModelRouter,
        model_name: str,
        session_store: RedisSessionStore,
        knowledge_store: KnowledgeStore,
        tool_registry: ToolRegistry,
        config: dict[str, Any],
        db_manager=None,
        hook_engine: HookEngine | None = None,
        subagent_pool=None,
    ):
        self.agent_id = agent_id
        self.model_router = model_router
        self.model_name = model_name
        self.session_store = session_store
        self.knowledge_store = knowledge_store
        self.tool_registry = tool_registry
        self.config = config
        self.db_manager = db_manager
        self.hook_engine = hook_engine or HookEngine()
        self.subagent_pool = subagent_pool

        # Operational state (loaded from database on initialization)
        self.status = "online"
        self.tasks_completed_today = 0
        self.budget_used_today = 0.0
        self._latencies: list[float] = []
        self._errors_today = 0
        self.circuit_breaker = CircuitBreaker()

        # Subagent capability flag
        self.can_spawn_subagents: bool = config.get("can_spawn_subagents", False)

    @property
    def circuit_breaker_state(self) -> str:
        return self.circuit_breaker.state

    @property
    def avg_latency_ms(self) -> float:
        if not self._latencies:
            return 0.0
        return sum(self._latencies[-100:]) / len(self._latencies[-100:])

    @property
    def error_rate(self) -> float:
        total = self.tasks_completed_today + self._errors_today
        if total == 0:
            return 0.0
        return self._errors_today / total

    @traceable(name="agent.execute")
    async def execute(
        self,
        task: str,
        context: dict[str, Any],
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Execute a task with full instrumentation.

        Flow:
        1. Fire PRE_EXECUTE hooks
        2. Check circuit breaker
        3. Check budget
        4. Build prompt with context
        5. Call LLM via model router
        6. Process tool calls (if any)
        7. Fire POST_EXECUTE hooks
        8. Track cost and latency
        9. Return structured result
        """
        start_time = time.monotonic()

        # Fire PRE_EXECUTE hooks
        if session_id:
            pre_context = HookContext(
                hook_type=HookType.PRE_EXECUTE,
                session_id=session_id,
                agent_id=self.agent_id,
                task=task,
                metadata={
                    "budget_limit": self.config["budget_limit_daily"],
                    "budget_used": self.budget_used_today,
                },
            )
            await self.hook_engine.fire(HookType.PRE_EXECUTE, pre_context)

        # Circuit breaker check
        if not self.circuit_breaker.can_execute():
            return {
                "status": "failed",
                "error": f"Agent {self.agent_id} circuit breaker is open",
                "response": "",
            }

        # Budget check
        if self.budget_used_today >= self.config["budget_limit_daily"]:
            return {
                "status": "failed",
                "error": f"Agent {self.agent_id} daily budget exhausted",
                "response": "",
            }

        try:
            # Build domain-specific prompt
            prompt = self.build_prompt(task=task, context=context)

            # Get available tools for this agent
            tools = self.tool_registry.get_tools(self.config.get("tools", []))

            # Call LLM
            response = await self.model_router.generate(
                model=self.model_name,
                prompt=prompt,
                tools=tools,
                max_tokens=self.config.get("max_tokens_per_task", 4096),
            )

            # Process any tool calls
            if response.tool_calls:
                tool_results = await self._execute_tools(
                    response.tool_calls,
                    session_id=session_id,
                )
                # Follow-up call with tool results
                response = await self.model_router.generate(
                    model=self.model_name,
                    prompt=prompt,
                    tool_results=tool_results,
                    max_tokens=self.config.get("max_tokens_per_task", 4096),
                )

            # Track metrics (keep last 100 latencies)
            elapsed_ms = (time.monotonic() - start_time) * 1000
            self._latencies.append(elapsed_ms)
            if len(self._latencies) > 100:
                self._latencies = self._latencies[-100:]
            self.tasks_completed_today += 1
            self.budget_used_today += response.cost
            self.circuit_breaker.record_success()

            # Fire POST_EXECUTE hooks
            if session_id:
                post_context = HookContext(
                    hook_type=HookType.POST_EXECUTE,
                    session_id=session_id,
                    agent_id=self.agent_id,
                    task=task,
                    result={"content": response.content, "tokens": response.total_tokens},
                )
                await self.hook_engine.fire(HookType.POST_EXECUTE, post_context)

            # Persist metrics to database if available
            if self.db_manager:
                await self._persist_metrics()

            return {
                "status": "success",
                "response": response.content,
                "tokens_used": response.total_tokens,
                "cost": response.cost,
                "latency_ms": elapsed_ms,
                "model": self.model_name,
                "agent_id": self.agent_id,
            }

        except Exception as e:
            self._errors_today += 1
            self.circuit_breaker.record_failure()
            elapsed_ms = (time.monotonic() - start_time) * 1000

            # Fire ON_ERROR hooks
            if session_id:
                error_context = HookContext(
                    hook_type=HookType.ON_ERROR,
                    session_id=session_id,
                    agent_id=self.agent_id,
                    task=task,
                    error=e,
                )
                await self.hook_engine.fire(HookType.ON_ERROR, error_context)

            logger.error(
                "Agent %s failed: %s (latency: %.0fms)",
                self.agent_id, str(e), elapsed_ms,
            )

            return {
                "status": "failed",
                "error": str(e),
                "response": "",
                "latency_ms": elapsed_ms,
                "agent_id": self.agent_id,
            }

    @abstractmethod
    def build_prompt(self, task: str, context: dict[str, Any]) -> str:
        """Build domain-specific prompt. Implemented by each specialized agent."""
        ...

    async def _execute_tools(
        self,
        tool_calls: list[dict],
        session_id: str | None = None,
    ) -> list[dict]:
        """Execute tool calls and return results."""
        results = []
        for call in tool_calls:
            tool = self.tool_registry.get_tool(call["name"])
            if tool:
                # Fire ON_TOOL_CALL hook
                if session_id:
                    tool_context = HookContext(
                        hook_type=HookType.ON_TOOL_CALL,
                        session_id=session_id,
                        agent_id=self.agent_id,
                        tool_name=call["name"],
                        tool_args=call.get("arguments", {}),
                    )
                    await self.hook_engine.fire(HookType.ON_TOOL_CALL, tool_context)

                result = await tool.execute(**call["arguments"])
                results.append({
                    "tool_call_id": call["id"],
                    "output": result,
                })
        return results

    async def spawn_subagent(
        self,
        config: "SubagentConfig",
        task: str,
    ) -> "SubagentResult":
        """
        Spawn a lightweight subagent to execute a subtask.

        Only available if can_spawn_subagents is True in config.

        Args:
            config: Subagent configuration
            task: Task description for the subagent

        Returns:
            SubagentResult with output and metadata
        """
        if not self.can_spawn_subagents or not self.subagent_pool:
            raise RuntimeError(
                f"Agent {self.agent_id} does not support subagent spawning"
            )

        # Cost rolls up to parent's budget
        result = await self.subagent_pool.spawn(
            parent_agent_id=self.agent_id,
            config=config,
            task=task,
        )

        # Track cost against parent's budget
        self.budget_used_today += result.cost

        return result

    async def _persist_metrics(self) -> None:
        """Persist agent metrics to database."""
        if not self.db_manager:
            return

        try:
            from src.db import AgentMetricRecord
            from sqlalchemy import select, update

            async with self.db_manager.get_session() as session:
                # Check if record exists
                stmt = select(AgentMetricRecord).where(
                    AgentMetricRecord.agent_id == self.agent_id
                )
                result = await session.execute(stmt)
                record = result.scalars().first()

                if record:
                    # Update existing record
                    stmt = update(AgentMetricRecord).where(
                        AgentMetricRecord.agent_id == self.agent_id
                    ).values(
                        latencies=self._latencies[-100:],
                        tasks_completed_today=self.tasks_completed_today,
                        budget_used_today=self.budget_used_today,
                        errors_today=self._errors_today,
                        circuit_breaker_state=self.circuit_breaker.state,
                        circuit_breaker_failure_count=self.circuit_breaker.failure_count,
                        circuit_breaker_last_failure=self.circuit_breaker.last_failure_time,
                    )
                    await session.execute(stmt)
                else:
                    # Create new record
                    record = AgentMetricRecord(
                        agent_id=self.agent_id,
                        latencies=self._latencies[-100:],
                        tasks_completed_today=self.tasks_completed_today,
                        budget_used_today=self.budget_used_today,
                        errors_today=self._errors_today,
                        circuit_breaker_state=self.circuit_breaker.state,
                        circuit_breaker_failure_count=self.circuit_breaker.failure_count,
                        circuit_breaker_last_failure=self.circuit_breaker.last_failure_time,
                    )
                    session.add(record)

                await session.commit()
        except Exception as e:
            logger.error("Failed to persist agent metrics: %s", str(e))

    async def shutdown(self) -> None:
        """Graceful shutdown — persist final metrics."""
        await self._persist_metrics()
        self.status = "offline"
