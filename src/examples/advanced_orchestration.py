"""
Advanced Orchestration Examples — Demonstrates new capabilities.

Shows how to use:
1. Hook system for custom behaviors
2. Subagent spawning for task decomposition
3. Evaluation framework for quality assessment
4. Memory consolidation for learning
"""

import asyncio
from datetime import datetime
from typing import Any

# Example 1: Setting up hooks for audit and escalation


async def example_hooks():
    """Demonstrates the hook system."""
    from src.hooks.engine import (
        HookEngine,
        Hook,
        HookType,
        HookContext,
        create_default_hooks,
    )

    engine = HookEngine()

    # Register built-in hooks
    for hook in create_default_hooks():
        engine.register(hook)

    # Create a custom hook for logging business metrics
    async def metrics_hook(context: HookContext) -> None:
        """Custom hook to log business metrics."""
        if context.hook_type == HookType.POST_EXECUTE:
            print(
                f"Task completed in session {context.session_id}: "
                f"{context.task[:50]}..."
            )

    custom_hook = Hook(
        name="business_metrics",
        hook_type=HookType.POST_EXECUTE,
        handler=metrics_hook,
        priority=50,
    )
    engine.register(custom_hook)

    # Fire some hooks
    context = HookContext(
        hook_type=HookType.SESSION_START,
        session_id="session_123",
        agent_id="claims",
        task="Process claim #CLM-5000",
    )
    await engine.fire(HookType.SESSION_START, context)

    # View metrics
    metrics = engine.get_metrics()
    print(f"Hook metrics: {metrics}")

    return engine


# Example 2: Spawning subagents for parallel task execution


async def example_subagent_pool():
    """Demonstrates subagent spawning."""
    from src.agents.subagent import (
        SubagentPool,
        SubagentConfig,
        DATA_FETCHER_CONFIG,
        ANALYZER_CONFIG,
        VALIDATOR_CONFIG,
    )
    from src.providers.router import ModelRouter
    from src.tools.registry import ToolRegistry

    # Create pool
    model_router = ModelRouter()
    tool_registry = ToolRegistry()
    pool = SubagentPool(
        model_router=model_router,
        tool_registry=tool_registry,
        max_concurrent_per_parent=3,
    )

    # Spawn a data fetcher subagent
    fetch_result = await pool.spawn(
        parent_agent_id="claims_agent",
        config=DATA_FETCHER_CONFIG,
        task="Retrieve claim details for CLM-5000 from database",
    )

    print(f"Data fetcher result: {fetch_result.output[:100]}...")
    print(f"Cost: ${fetch_result.cost:.2f}, Latency: {fetch_result.latency_ms:.0f}ms")

    # Spawn multiple subagents in parallel
    analyzer_tasks = [
        (ANALYZER_CONFIG, "Analyze medical records for CLM-5000"),
        (ANALYZER_CONFIG, "Analyze claim history patterns"),
        (VALIDATOR_CONFIG, "Validate extracted data against schema"),
    ]

    results = await pool.spawn_parallel(
        parent_agent_id="claims_agent",
        tasks=analyzer_tasks,
    )

    total_cost = sum(r.cost for r in results)
    print(f"Parallel tasks completed: {len(results)} subagents, total cost: ${total_cost:.2f}")

    return pool


# Example 3: Running evaluation suite


async def example_eval_suite():
    """Demonstrates the evaluation framework."""
    from src.evals.runner import (
        EvalSuite,
        semantic_similarity_evaluator,
        hallucination_detector,
    )

    suite = EvalSuite()

    # Register evaluators
    suite.add_evaluator(
        name="semantic_similarity",
        fn=semantic_similarity_evaluator,
        weight=1.0,
    )
    suite.add_evaluator(
        name="hallucination_detection",
        fn=hallucination_detector,
        weight=1.0,
    )

    # Create test dataset
    dataset = [
        {
            "input": "What is the status of claim CLM-5000?",
            "expected": "Claim CLM-5000 is approved and pending payment",
            "metadata": {"cost": 0.05},
        },
        {
            "input": "Summarize the policy details",
            "expected": "Standard auto policy with collision and liability coverage",
            "metadata": {"cost": 0.08},
        },
    ]

    # Mock agent function
    async def mock_agent(user_input: str) -> str:
        """Mock agent that returns plausible responses."""
        if "status" in user_input.lower():
            return "Claim CLM-5000 is approved and pending payment processing"
        return "Standard auto policy with collision coverage and liability protection"

    # Run evaluators
    results = await suite.run(dataset=dataset, agent_fn=mock_agent)

    # Generate report
    report = suite.generate_report(results)
    print(report)

    return results


# Example 4: Memory consolidation


async def example_memory_consolidation():
    """Demonstrates memory consolidation."""
    from src.memory.consolidation import MemoryConsolidator

    consolidator = MemoryConsolidator()

    # Consolidate a session
    summary = await consolidator.consolidate_session(
        session_id="session_123",
        min_messages=5,
    )

    if summary:
        print(f"Consolidated session {summary.session_id}")
        print(f"Key facts: {summary.key_facts[:3]}")
        print(f"Agents used: {summary.agents_used}")
        print(f"Cost: ${summary.total_cost:.2f}")

    # Find similar sessions
    similar = await consolidator.find_similar_sessions(
        query="Process auto insurance claim",
        limit=5,
    )
    print(f"Found {len(similar)} similar sessions")

    # Extract patterns
    patterns = await consolidator.extract_patterns(sample_size=100)
    print(f"Identified {len(patterns)} patterns")
    for pattern in patterns:
        print(f"  - {pattern.description}")

    return consolidator


# Example 5: Full orchestration with hooks and subagents


async def example_full_orchestration():
    """Demonstrates integrated orchestration with new features."""
    from src.hooks.engine import HookEngine, Hook, HookType, HookContext, create_default_hooks
    from src.agents.subagent import SubagentPool
    from src.providers.router import ModelRouter
    from src.tools.registry import ToolRegistry

    # 1. Set up hook engine
    hook_engine = HookEngine()
    for hook in create_default_hooks():
        hook_engine.register(hook)

    # Custom escalation hook
    async def custom_escalation_hook(context: HookContext) -> None:
        if context.hook_type == HookType.ON_ESCALATION:
            print(f"ESCALATION: Session {context.session_id} requires human review")

    hook_engine.register(
        Hook(
            name="custom_escalation",
            hook_type=HookType.ON_ESCALATION,
            handler=custom_escalation_hook,
            priority=100,
        )
    )

    # 2. Set up subagent pool
    model_router = ModelRouter()
    tool_registry = ToolRegistry()
    subagent_pool = SubagentPool(
        model_router=model_router,
        tool_registry=tool_registry,
    )

    # 3. Simulate orchestration flow
    session_id = "complex_claim_123"

    # Fire SESSION_START
    await hook_engine.fire(
        HookType.SESSION_START,
        HookContext(
            hook_type=HookType.SESSION_START,
            session_id=session_id,
            task="Process complex insurance claim",
        ),
    )

    # Fire PRE_EXECUTE
    await hook_engine.fire(
        HookType.PRE_EXECUTE,
        HookContext(
            hook_type=HookType.PRE_EXECUTE,
            session_id=session_id,
            metadata={"budget_limit": 100.0, "budget_used": 25.0},
        ),
    )

    # Fire ON_TOOL_CALL
    await hook_engine.fire(
        HookType.ON_TOOL_CALL,
        HookContext(
            hook_type=HookType.ON_TOOL_CALL,
            session_id=session_id,
            agent_id="claims_agent",
            tool_name="database_query",
            tool_args={"query": "SELECT * FROM claims WHERE id = 'CLM-5000'"},
        ),
    )

    # Fire POST_EXECUTE
    await hook_engine.fire(
        HookType.POST_EXECUTE,
        HookContext(
            hook_type=HookType.POST_EXECUTE,
            session_id=session_id,
            result={"response": "Claim processed successfully"},
        ),
    )

    # Fire SESSION_END
    await hook_engine.fire(
        HookType.SESSION_END,
        HookContext(
            hook_type=HookType.SESSION_END,
            session_id=session_id,
        ),
    )

    print("Full orchestration flow completed")
    metrics = hook_engine.get_metrics()
    print(f"Hook execution metrics: {metrics}")


# Main runner


async def main():
    """Run all examples."""
    print("=" * 80)
    print("ADVANCED ORCHESTRATION EXAMPLES")
    print("=" * 80)

    print("\n[1] Hook System Example")
    print("-" * 80)
    try:
        await example_hooks()
    except Exception as e:
        print(f"Note: {type(e).__name__}: {str(e)[:100]}")

    print("\n[2] Subagent Pool Example")
    print("-" * 80)
    try:
        await example_subagent_pool()
    except Exception as e:
        print(f"Note: {type(e).__name__}: {str(e)[:100]}")

    print("\n[3] Evaluation Suite Example")
    print("-" * 80)
    try:
        await example_eval_suite()
    except Exception as e:
        print(f"Note: {type(e).__name__}: {str(e)[:100]}")

    print("\n[4] Memory Consolidation Example")
    print("-" * 80)
    try:
        await example_memory_consolidation()
    except Exception as e:
        print(f"Note: {type(e).__name__}: {str(e)[:100]}")

    print("\n[5] Full Orchestration Example")
    print("-" * 80)
    try:
        await example_full_orchestration()
    except Exception as e:
        print(f"Note: {type(e).__name__}: {str(e)[:100]}")

    print("\n" + "=" * 80)
    print("Examples completed")


if __name__ == "__main__":
    asyncio.run(main())
