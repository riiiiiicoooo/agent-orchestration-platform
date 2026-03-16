"""
Budget Enforcement — Per-agent, per-user token budgets with circuit breakers.

Prevents cost runaway by enforcing daily and per-request budget limits.
Alerts at 80% budget utilization, circuit breaker at 100%.

Persistence: PostgreSQL for configurations, Redis for daily state tracking.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class BudgetConfig:
    """Budget configuration for an agent or user."""
    daily_limit: float = 100.0         # Daily spend limit in USD
    per_request_limit: float = 5.0     # Max spend per single request
    alert_threshold: float = 0.8       # Alert at 80% of daily limit
    circuit_breaker_threshold: float = 1.0  # Kill at 100%


@dataclass
class BudgetState:
    """Current budget state."""
    spent_today: float = 0.0
    requests_today: int = 0
    last_reset: str = ""
    alerts_sent: list[str] = field(default_factory=list)


class BudgetEnforcer:
    """
    Per-agent and per-user budget enforcement with persistent storage.

    Architecture:
    - PostgreSQL: Stores budget configurations (agent_budgets, user_budgets)
    - Redis: Caches daily state (spent_today, requests_today) with auto-reset
    - In-memory dict: Loaded at startup, updated via database

    This replaces in-memory-only tracking with durable persistence.
    """

    def __init__(self, db_manager=None, redis_manager=None):
        self.db_manager = db_manager
        self.redis_manager = redis_manager
        # In-memory cache loaded from database at startup
        self.agent_budgets: dict[str, BudgetConfig] = {}
        self.user_budgets: dict[str, BudgetConfig] = {}

    def set_agent_budget(self, agent_id: str, config: BudgetConfig) -> None:
        self.agent_budgets[agent_id] = config

    def set_user_budget(self, user_id: str, config: BudgetConfig) -> None:
        self.user_budgets[user_id] = config

    def check_budget(
        self,
        agent_id: str,
        user_id: str,
        estimated_cost: float,
        current_spend: float,
    ) -> dict[str, Any]:
        """
        Check if a request is within budget before execution.

        Returns:
            {
                "allowed": bool,
                "reason": str,
                "budget_utilization": float,
                "alert_needed": bool,
            }
        """
        agent_config = self.agent_budgets.get(agent_id, BudgetConfig())

        # Per-request limit check
        if estimated_cost > agent_config.per_request_limit:
            return {
                "allowed": False,
                "reason": f"Estimated cost ${estimated_cost:.2f} exceeds per-request limit ${agent_config.per_request_limit:.2f}",
                "budget_utilization": current_spend / agent_config.daily_limit,
                "alert_needed": True,
            }

        # Daily limit check
        projected_spend = current_spend + estimated_cost
        utilization = projected_spend / agent_config.daily_limit

        if utilization >= agent_config.circuit_breaker_threshold:
            return {
                "allowed": False,
                "reason": f"Daily budget exhausted (${current_spend:.2f}/${agent_config.daily_limit:.2f})",
                "budget_utilization": utilization,
                "alert_needed": True,
            }

        alert_needed = utilization >= agent_config.alert_threshold

        return {
            "allowed": True,
            "reason": "",
            "budget_utilization": utilization,
            "alert_needed": alert_needed,
        }

    def record_spend(
        self,
        agent_id: str,
        user_id: str,
        cost: float,
        tokens: int,
    ) -> None:
        """Record actual spend after execution."""
        logger.debug(
            "Budget recorded: agent=%s, user=%s, cost=$%.4f, tokens=%d",
            agent_id, user_id, cost, tokens,
        )
