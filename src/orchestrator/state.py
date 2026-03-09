"""
Orchestrator State — Shared state schema for the LangGraph workflow.

Defines the data structures passed between nodes in the orchestration graph.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Intent:
    """Classified intent from user input."""
    domain: str                    # claims, underwriting, customer_service, document, analytics
    complexity: str                # simple, chain, parallel
    target_agents: list[str]       # Agent IDs to route to
    confidence: float              # Classification confidence (0.0 - 1.0)
    requires_human_review: bool    # Whether output needs HITL gate
    estimated_cost: float          # Estimated LLM cost for this request
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentAssignment:
    """Agent assignment within a task."""
    agent_id: str
    priority: int = 0              # Execution order (for chain mode)
    max_retries: int = 2
    timeout_seconds: int = 30


@dataclass
class GuardrailResult:
    """Result of a guardrail check."""
    blocked: bool = False
    reason: str = ""
    severity: str = "info"         # info, warning, critical
    details: dict[str, Any] = field(default_factory=dict)
    message: str = ""


@dataclass
class TaskResult:
    """Final result of an orchestrated task."""
    success: bool = False
    response: str = ""
    agent_outputs: dict[str, Any] = field(default_factory=dict)
    total_tokens: int = 0
    total_cost: float = 0.0
    latency_ms: int = 0
    blocked_by: str | None = None
    guardrail_details: dict[str, Any] | None = None
    escalated: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class OrchestratorState:
    """
    Full state passed through the LangGraph orchestration graph.

    Each node reads and updates this state. LangGraph checkpoints
    the state between nodes for durability and replay.
    """
    # Input
    user_input: str = ""
    session_id: str = ""
    user_id: str = ""

    # Classification
    intent: Intent | None = None

    # Context (retrieved from memory)
    session_context: dict[str, Any] = field(default_factory=dict)
    conversation_history: list[dict[str, Any]] = field(default_factory=list)
    relevant_knowledge: list[dict[str, Any]] = field(default_factory=list)

    # Execution
    assignments: list[AgentAssignment] = field(default_factory=list)
    agent_outputs: dict[str, Any] = field(default_factory=dict)
    validation_errors: list[str] = field(default_factory=list)

    # Results
    result: TaskResult | None = None
    post_check_result: GuardrailResult | None = None

    # Retry tracking
    retry_count: int = 0
    max_retries: int = 2
