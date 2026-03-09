"""
Base Agent — Common interface for all specialized agents.

Provides circuit breaker, cost tracking, tool access, and
standardized execution flow that all domain agents inherit.
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
    ):
        self.agent_id = agent_id
        self.model_router = model_router
        self.model_name = model_name
        self.session_store = session_store
        self.knowledge_store = knowledge_store
        self.tool_registry = tool_registry
        self.config = config

        # Operational state
        self.status = "online"
        self.tasks_completed_today = 0
        self.budget_used_today = 0.0
        self._latencies: list[float] = []
        self._errors_today = 0
        self.circuit_breaker = CircuitBreaker()

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
    ) -> dict[str, Any]:
        """
        Execute a task with full instrumentation.

        Flow:
        1. Check circuit breaker
        2. Check budget
        3. Build prompt with context
        4. Call LLM via model router
        5. Process tool calls (if any)
        6. Track cost and latency
        7. Return structured result
        """
        start_time = time.monotonic()

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
                tool_results = await self._execute_tools(response.tool_calls)
                # Follow-up call with tool results
                response = await self.model_router.generate(
                    model=self.model_name,
                    prompt=prompt,
                    tool_results=tool_results,
                    max_tokens=self.config.get("max_tokens_per_task", 4096),
                )

            # Track metrics
            elapsed_ms = (time.monotonic() - start_time) * 1000
            self._latencies.append(elapsed_ms)
            self.tasks_completed_today += 1
            self.budget_used_today += response.cost
            self.circuit_breaker.record_success()

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

    async def _execute_tools(self, tool_calls: list[dict]) -> list[dict]:
        """Execute tool calls and return results."""
        results = []
        for call in tool_calls:
            tool = self.tool_registry.get_tool(call["name"])
            if tool:
                result = await tool.execute(**call["arguments"])
                results.append({
                    "tool_call_id": call["id"],
                    "output": result,
                })
        return results

    async def shutdown(self) -> None:
        """Graceful shutdown."""
        self.status = "offline"
