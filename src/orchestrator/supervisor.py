"""
Supervisor Agent — Central orchestration coordinator.

Decomposes incoming tasks, routes to specialized agents, enforces guardrails,
and aggregates results. Uses LangGraph for stateful workflow execution
with checkpointing and human-in-the-loop gates.
"""

import logging
import time
from typing import Any

from langsmith import traceable

from src.orchestrator.state import OrchestratorState, TaskResult, AgentAssignment
from src.orchestrator.router import IntentRouter
from src.orchestrator.graph import build_orchestration_graph
from src.agents.base import BaseAgent
from src.agents.claims import ClaimsAgent
from src.agents.underwriting import UnderwritingAgent
from src.agents.customer_service import CustomerServiceAgent
from src.agents.document import DocumentProcessingAgent
from src.agents.analytics import AnalyticsAgent
from src.guardrails.engine import GuardrailEngine
from src.tools.registry import ToolRegistry
from src.memory.session import RedisSessionStore
from src.memory.conversation import ConversationStore
from src.memory.knowledge import KnowledgeStore
from src.providers.router import ModelRouter

logger = logging.getLogger(__name__)


class SupervisorAgent:
    """
    Central supervisor that coordinates all specialized agents.

    Responsibilities:
    1. Classify incoming requests (intent detection via Haiku)
    2. Decompose complex tasks into subtasks
    3. Route subtasks to appropriate specialized agents
    4. Enforce guardrails on all agent outputs
    5. Aggregate results and return unified response
    6. Track cost and latency per agent per task
    """

    def __init__(
        self,
        model_router: ModelRouter,
        session_store: RedisSessionStore,
        conversation_store: ConversationStore,
        knowledge_store: KnowledgeStore,
    ):
        self.model_router = model_router
        self.session_store = session_store
        self.conversation_store = conversation_store
        self.knowledge_store = knowledge_store

        # Initialize components
        self.intent_router = IntentRouter(model_router=model_router)
        self.guardrail_engine = GuardrailEngine()
        self.tool_registry = ToolRegistry()

        # Agent registry — maps agent_id to agent instance
        self.agents: dict[str, BaseAgent] = {}

        # LangGraph orchestration graph
        self.graph = None

    async def initialize(self) -> None:
        """Register all specialized agents and build the orchestration graph."""
        agent_configs = [
            ("claims", ClaimsAgent, "claude-3.5-sonnet", {
                "max_tokens_per_task": 4096,
                "budget_limit_daily": 150.0,
                "tools": ["database_query", "document_search", "claims_api"],
            }),
            ("underwriting", UnderwritingAgent, "gpt-4o", {
                "max_tokens_per_task": 8192,
                "budget_limit_daily": 200.0,
                "tools": ["database_query", "risk_model", "policy_lookup"],
            }),
            ("customer_service", CustomerServiceAgent, "claude-3-haiku", {
                "max_tokens_per_task": 2048,
                "budget_limit_daily": 50.0,
                "tools": ["faq_search", "status_lookup", "ticket_create"],
            }),
            ("document", DocumentProcessingAgent, "claude-3.5-sonnet", {
                "max_tokens_per_task": 8192,
                "budget_limit_daily": 180.0,
                "tools": ["ocr_extract", "document_classify", "data_normalize"],
            }),
            ("analytics", AnalyticsAgent, "gpt-4o", {
                "max_tokens_per_task": 16384,
                "budget_limit_daily": 120.0,
                "tools": ["database_query", "report_generate", "trend_analyze"],
            }),
        ]

        for agent_id, agent_class, model, config in agent_configs:
            agent = agent_class(
                agent_id=agent_id,
                model_router=self.model_router,
                model_name=model,
                session_store=self.session_store,
                knowledge_store=self.knowledge_store,
                tool_registry=self.tool_registry,
                config=config,
            )
            self.agents[agent_id] = agent
            logger.info("Registered agent: %s (model: %s)", agent_id, model)

        # Build the LangGraph orchestration graph
        self.graph = build_orchestration_graph(
            agents=self.agents,
            guardrail_engine=self.guardrail_engine,
        )

        logger.info(
            "Supervisor initialized — %d agents, %d tools",
            len(self.agents),
            len(self.tool_registry),
        )

    @traceable(name="supervisor.process_request")
    async def process_request(
        self,
        user_input: str,
        session_id: str,
        user_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> TaskResult:
        """
        Main entry point — process a user request through the orchestration pipeline.

        Flow:
        1. Classify intent (Haiku, <200ms)
        2. Check guardrails (pre-execution)
        3. Retrieve relevant context from memory
        4. Route to agent(s)
        5. Check guardrails (post-execution)
        6. Store results in memory
        7. Return aggregated response
        """
        start_time = time.monotonic()

        # Step 1: Classify intent
        intent = await self.intent_router.classify(
            user_input=user_input,
            session_context=await self.session_store.get_context(session_id),
        )

        logger.info(
            "Intent classified: domain=%s, complexity=%s, agents=%s",
            intent.domain,
            intent.complexity,
            intent.target_agents,
        )

        # Step 2: Pre-execution guardrails
        pre_check = await self.guardrail_engine.check_input(
            user_input=user_input,
            intent=intent,
            user_id=user_id,
        )
        if pre_check.blocked:
            return TaskResult(
                success=False,
                response=pre_check.message,
                blocked_by="guardrail_pre_check",
                guardrail_details=pre_check.details,
                latency_ms=int((time.monotonic() - start_time) * 1000),
            )

        # Step 3: Retrieve context from memory
        session_context = await self.session_store.get_context(session_id)
        conversation_history = await self.conversation_store.get_recent(
            session_id=session_id,
            limit=10,
        )
        relevant_knowledge = await self.knowledge_store.search(
            query=user_input,
            domain=intent.domain,
            top_k=5,
        )

        # Step 4: Build orchestrator state and execute graph
        state = OrchestratorState(
            user_input=user_input,
            session_id=session_id,
            user_id=user_id,
            intent=intent,
            session_context=session_context,
            conversation_history=conversation_history,
            relevant_knowledge=relevant_knowledge,
            assignments=[
                AgentAssignment(agent_id=agent_id, priority=idx)
                for idx, agent_id in enumerate(intent.target_agents)
            ],
        )

        # Execute the LangGraph orchestration graph
        result = await self.graph.ainvoke(state)

        # Step 5: Post-execution guardrails
        post_check = await self.guardrail_engine.check_output(
            response=result.response,
            intent=intent,
            agent_outputs=result.agent_outputs,
        )
        if post_check.blocked:
            # Escalate to human review instead of returning blocked content
            await self._escalate_to_human(
                state=state,
                result=result,
                guardrail_result=post_check,
            )
            return TaskResult(
                success=False,
                response="This request requires human review before a response can be provided.",
                blocked_by="guardrail_post_check",
                guardrail_details=post_check.details,
                escalated=True,
                latency_ms=int((time.monotonic() - start_time) * 1000),
            )

        # Step 6: Store results in memory
        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        await self.session_store.update_context(
            session_id=session_id,
            latest_intent=intent.domain,
            latest_response_summary=result.response[:200],
        )
        await self.conversation_store.append(
            session_id=session_id,
            user_input=user_input,
            response=result.response,
            intent=intent,
            agents_used=intent.target_agents,
            latency_ms=elapsed_ms,
            token_usage=result.total_tokens,
            cost=result.total_cost,
        )

        result.latency_ms = elapsed_ms
        return result

    async def _escalate_to_human(self, state, result, guardrail_result) -> None:
        """Create a human-in-the-loop escalation ticket."""
        logger.warning(
            "Escalating to human review — session=%s, reason=%s",
            state.session_id,
            guardrail_result.reason,
        )
        # In production: creates Trigger.dev job for human review queue
        # with full context, agent outputs, and guardrail details

    async def get_agent_status(self) -> dict[str, Any]:
        """Return real-time health status of all agents."""
        statuses = {}
        for agent_id, agent in self.agents.items():
            statuses[agent_id] = {
                "status": agent.status,
                "tasks_completed_today": agent.tasks_completed_today,
                "budget_used_today": agent.budget_used_today,
                "budget_limit_daily": agent.config["budget_limit_daily"],
                "avg_latency_ms": agent.avg_latency_ms,
                "error_rate": agent.error_rate,
                "circuit_breaker": agent.circuit_breaker_state,
            }
        return statuses

    async def shutdown(self) -> None:
        """Graceful shutdown — flush pending state, close connections."""
        for agent in self.agents.values():
            await agent.shutdown()
        logger.info("Supervisor shutdown complete.")
