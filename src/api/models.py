"""
API Models — Pydantic request/response models for API validation.
"""

from pydantic import BaseModel, Field
from typing import Any


class TaskRequest(BaseModel):
    """Request to submit a task for agent orchestration."""
    input: str = Field(..., description="User input or task description")
    session_id: str = Field(..., description="Session identifier")
    user_id: str = Field(..., description="User identifier")
    metadata: dict[str, Any] | None = Field(None, description="Optional metadata")


class TaskResponse(BaseModel):
    """Response from task orchestration."""
    success: bool
    response: str
    agents_used: list[str] = []
    total_tokens: int = 0
    total_cost: float = 0.0
    latency_ms: int = 0
    escalated: bool = False
    blocked_by: str | None = None


class AgentStatusResponse(BaseModel):
    """Status of all registered agents."""
    agents: dict[str, Any]


class CostSummaryResponse(BaseModel):
    """Cost attribution summary."""
    total_cost: float = 0.0
    by_model: dict[str, float] = {}
    by_provider: dict[str, float] = {}


class HealthResponse(BaseModel):
    """System health check response."""
    status: str
    total_agents: int
    healthy_agents: int
    active_sessions: int
    uptime_seconds: int
