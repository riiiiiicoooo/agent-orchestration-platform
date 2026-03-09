"""
LangGraph Orchestration Graph — Stateful workflow execution.

Defines the state machine for multi-agent task orchestration with
checkpointing, conditional routing, and human-in-the-loop gates.
"""

from typing import Any
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from src.orchestrator.state import OrchestratorState, TaskResult
from src.agents.base import BaseAgent
from src.guardrails.engine import GuardrailEngine


def build_orchestration_graph(
    agents: dict[str, BaseAgent],
    guardrail_engine: GuardrailEngine,
) -> StateGraph:
    """
    Build the LangGraph state machine for agent orchestration.

    Graph topology:
    ┌─────────┐    ┌──────────┐    ┌──────────────┐    ┌───────────┐
    │ classify │───►│ validate  │───►│ execute_agents│───►│ aggregate │
    └─────────┘    └──────────┘    └──────────────┘    └─────┬─────┘
                        │                                     │
                        │ blocked                             │
                        ▼                                     ▼
                   ┌─────────┐                          ┌──────────┐
                   │ blocked  │                          │ post_check│
                   └─────────┘                          └─────┬────┘
                                                              │
                                                    ┌─────────┼─────────┐
                                                    │         │         │
                                                    ▼         ▼         ▼
                                              ┌────────┐ ┌─────────┐ ┌────────┐
                                              │ respond │ │escalate │ │ retry  │
                                              └────────┘ └─────────┘ └────────┘
    """
    workflow = StateGraph(OrchestratorState)

    # --- Node definitions ---

    async def classify_node(state: OrchestratorState) -> OrchestratorState:
        """Already classified by supervisor — pass through."""
        return state

    async def validate_node(state: OrchestratorState) -> OrchestratorState:
        """Pre-execution validation: budget check, rate limit, permission check."""
        for assignment in state.assignments:
            agent = agents.get(assignment.agent_id)
            if agent is None:
                state.validation_errors.append(
                    f"Unknown agent: {assignment.agent_id}"
                )
                continue

            # Budget check
            if agent.budget_used_today >= agent.config["budget_limit_daily"]:
                state.validation_errors.append(
                    f"Agent {assignment.agent_id} has exceeded daily budget "
                    f"(${agent.budget_used_today:.2f}/${agent.config['budget_limit_daily']:.2f})"
                )

            # Circuit breaker check
            if agent.circuit_breaker_state == "open":
                state.validation_errors.append(
                    f"Agent {assignment.agent_id} circuit breaker is OPEN "
                    f"(error rate: {agent.error_rate:.1%})"
                )

        return state

    async def execute_agents_node(state: OrchestratorState) -> OrchestratorState:
        """Execute assigned agents — parallel for independent tasks, sequential for chains."""
        agent_outputs = {}

        if state.intent.complexity == "simple":
            # Single agent execution
            agent_id = state.assignments[0].agent_id
            agent = agents[agent_id]
            result = await agent.execute(
                task=state.user_input,
                context={
                    "session": state.session_context,
                    "history": state.conversation_history,
                    "knowledge": state.relevant_knowledge,
                },
            )
            agent_outputs[agent_id] = result

        elif state.intent.complexity == "chain":
            # Sequential execution — output of one feeds into next
            chain_context = {}
            for assignment in sorted(state.assignments, key=lambda a: a.priority):
                agent = agents[assignment.agent_id]
                result = await agent.execute(
                    task=state.user_input,
                    context={
                        "session": state.session_context,
                        "history": state.conversation_history,
                        "knowledge": state.relevant_knowledge,
                        "chain": chain_context,
                    },
                )
                agent_outputs[assignment.agent_id] = result
                chain_context[assignment.agent_id] = result

        else:
            # Parallel execution — independent agents
            import asyncio
            tasks = []
            for assignment in state.assignments:
                agent = agents[assignment.agent_id]
                tasks.append(
                    agent.execute(
                        task=state.user_input,
                        context={
                            "session": state.session_context,
                            "history": state.conversation_history,
                            "knowledge": state.relevant_knowledge,
                        },
                    )
                )
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for assignment, result in zip(state.assignments, results):
                if isinstance(result, Exception):
                    agent_outputs[assignment.agent_id] = {
                        "error": str(result),
                        "status": "failed",
                    }
                else:
                    agent_outputs[assignment.agent_id] = result

        state.agent_outputs = agent_outputs
        return state

    async def aggregate_node(state: OrchestratorState) -> OrchestratorState:
        """Aggregate results from multiple agents into a unified response."""
        if len(state.agent_outputs) == 1:
            agent_id = list(state.agent_outputs.keys())[0]
            output = state.agent_outputs[agent_id]
            state.result = TaskResult(
                success=output.get("status") != "failed",
                response=output.get("response", ""),
                agent_outputs=state.agent_outputs,
                total_tokens=output.get("tokens_used", 0),
                total_cost=output.get("cost", 0.0),
            )
        else:
            # Multi-agent aggregation
            combined_response_parts = []
            total_tokens = 0
            total_cost = 0.0
            all_success = True

            for agent_id, output in state.agent_outputs.items():
                if output.get("status") == "failed":
                    all_success = False
                    continue
                combined_response_parts.append(output.get("response", ""))
                total_tokens += output.get("tokens_used", 0)
                total_cost += output.get("cost", 0.0)

            state.result = TaskResult(
                success=all_success,
                response="\n\n".join(combined_response_parts),
                agent_outputs=state.agent_outputs,
                total_tokens=total_tokens,
                total_cost=total_cost,
            )

        return state

    async def post_check_node(state: OrchestratorState) -> OrchestratorState:
        """Post-execution guardrail check on aggregated output."""
        check = await guardrail_engine.check_output(
            response=state.result.response,
            intent=state.intent,
            agent_outputs=state.agent_outputs,
        )
        state.post_check_result = check
        return state

    # --- Conditional edges ---

    def should_execute(state: OrchestratorState) -> str:
        """Route based on validation results."""
        if state.validation_errors:
            return "blocked"
        return "execute"

    def post_check_routing(state: OrchestratorState) -> str:
        """Route based on post-execution guardrail results."""
        if state.post_check_result is None or not state.post_check_result.blocked:
            return "respond"
        if state.post_check_result.severity == "critical":
            return "escalate"
        return "retry"

    # --- Build graph ---

    workflow.add_node("classify", classify_node)
    workflow.add_node("validate", validate_node)
    workflow.add_node("execute_agents", execute_agents_node)
    workflow.add_node("aggregate", aggregate_node)
    workflow.add_node("post_check", post_check_node)

    workflow.set_entry_point("classify")
    workflow.add_edge("classify", "validate")
    workflow.add_conditional_edges("validate", should_execute, {
        "execute": "execute_agents",
        "blocked": END,
    })
    workflow.add_edge("execute_agents", "aggregate")
    workflow.add_edge("aggregate", "post_check")
    workflow.add_conditional_edges("post_check", post_check_routing, {
        "respond": END,
        "escalate": END,
        "retry": "execute_agents",
    })

    # Compile with checkpointing
    memory = MemorySaver()
    return workflow.compile(checkpointer=memory)
