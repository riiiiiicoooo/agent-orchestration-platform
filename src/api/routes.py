"""
API Routes — FastAPI endpoint definitions for the orchestration platform.

Provides REST API for task submission, agent management, cost tracking,
and system health monitoring. All list endpoints include pagination.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request, HTTPException, Query
from src.api.models import (
    TaskRequest,
    TaskResponse,
    AgentStatusResponse,
    CostSummaryResponse,
    HealthResponse,
)
from src.db import PaginationParams

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/tasks", response_model=TaskResponse)
async def submit_task(request: Request, task: TaskRequest) -> TaskResponse:
    """
    Submit a task for agent orchestration.

    The supervisor agent will:
    1. Classify intent (domain, complexity)
    2. Route to appropriate agent(s)
    3. Execute with guardrail checks
    4. Return aggregated response
    """
    supervisor = request.app.state.supervisor

    result = await supervisor.process_request(
        user_input=task.input,
        session_id=task.session_id,
        user_id=task.user_id,
        metadata=task.metadata,
    )

    return TaskResponse(
        success=result.success,
        response=result.response,
        agents_used=list(result.agent_outputs.keys()),
        total_tokens=result.total_tokens,
        total_cost=result.total_cost,
        latency_ms=result.latency_ms,
        escalated=result.escalated,
        blocked_by=result.blocked_by,
    )


@router.get("/agents/status", response_model=AgentStatusResponse)
async def get_agent_status(request: Request) -> AgentStatusResponse:
    """Get real-time status of all registered agents."""
    supervisor = request.app.state.supervisor
    statuses = await supervisor.get_agent_status()
    return AgentStatusResponse(agents=statuses)


@router.get("/cost/summary", response_model=CostSummaryResponse)
async def get_cost_summary(request: Request) -> CostSummaryResponse:
    """Get current cost attribution across agents and providers."""
    model_router = request.app.state.model_router
    summary = model_router.get_cost_summary()
    return CostSummaryResponse(**summary)


@router.get("/health", response_model=HealthResponse)
async def health_check(request: Request) -> HealthResponse:
    """System health check — agent status, memory stores, providers."""
    supervisor = request.app.state.supervisor
    session_store = request.app.state.session_store

    active_sessions = await session_store.get_active_sessions()
    agent_statuses = await supervisor.get_agent_status()

    healthy_agents = sum(
        1 for s in agent_statuses.values()
        if s.get("status") == "online" and s.get("circuit_breaker") == "closed"
    )

    return HealthResponse(
        status="healthy" if healthy_agents == len(agent_statuses) else "degraded",
        total_agents=len(agent_statuses),
        healthy_agents=healthy_agents,
        active_sessions=active_sessions,
        uptime_seconds=0,  # In production: track since startup
    )


@router.post("/agents/{agent_id}/reset")
async def reset_agent(request: Request, agent_id: str) -> dict[str, Any]:
    """Reset an agent's circuit breaker and daily counters."""
    supervisor = request.app.state.supervisor

    if agent_id not in supervisor.agents:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    agent = supervisor.agents[agent_id]
    agent.circuit_breaker.state = "closed"
    agent.circuit_breaker.failure_count = 0
    agent._errors_today = 0
    agent.status = "online"

    return {"status": "reset", "agent_id": agent_id}


@router.get("/knowledge/{domain}/stats")
async def get_knowledge_stats(request: Request, domain: str) -> dict[str, Any]:
    """Get statistics for a knowledge domain."""
    knowledge_store = request.app.state.knowledge_store
    return await knowledge_store.get_domain_stats(domain)


@router.get("/cost/history")
async def get_cost_history(
    request: Request,
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=100, description="Number of records to return"),
) -> dict[str, Any]:
    """
    Get paginated cost history with model and provider breakdown.

    Pagination:
    - skip: Number of records to skip (default: 0)
    - limit: Max records per page (default: 20, max: 100)
    """
    db_manager = request.app.state.db_manager

    try:
        from sqlalchemy import select
        from src.db import CostRecord

        async with db_manager.get_session() as session:
            # Get total count
            stmt = select(CostRecord).order_by(CostRecord.created_at.desc())
            result = await session.execute(stmt)
            records = result.scalars().all()
            total = len(records)

            # Apply pagination
            paginated = records[skip:skip + limit]

            return {
                "total": total,
                "skip": skip,
                "limit": limit,
                "records": [
                    {
                        "model": r.model_name,
                        "provider": r.provider_name,
                        "cost": r.cost,
                        "tokens": r.tokens,
                        "created_at": r.created_at.isoformat(),
                    }
                    for r in paginated
                ],
            }
    except Exception as e:
        logger.error("Failed to fetch cost history: %s", str(e))
        return {"total": 0, "skip": skip, "limit": limit, "records": []}


@router.get("/rate-limits/{user_id}")
async def get_user_rate_limit_status(
    request: Request,
    user_id: str,
) -> dict[str, Any]:
    """Get current rate limit status for a user."""
    redis_manager = request.app.state.redis_manager

    try:
        timestamps = await redis_manager.get_request_timestamps(user_id)
        import time
        now = time.time()
        minute_ago = now - 60

        recent = [t for t in timestamps if t > minute_ago]
        return {
            "user_id": user_id,
            "requests_in_last_minute": len(recent),
            "total_tracked_requests": len(timestamps),
        }
    except Exception as e:
        logger.error("Failed to fetch rate limit status: %s", str(e))
        return {
            "user_id": user_id,
            "requests_in_last_minute": 0,
            "total_tracked_requests": 0,
        }
