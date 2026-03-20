# Agent Orchestration Platform — Upgrade Guide

## Overview

This document describes the major upgrades to the Agent Orchestration Platform, enabling senior-level agent orchestration patterns inspired by the "Everything Claude Code" project.

## What's New

### 1. Hook System (`src/hooks/engine.py`)

**Purpose**: Extensible event system for agent lifecycle management without polluting agent code.

**Features**:
- 7 hook types: `PRE_EXECUTE`, `POST_EXECUTE`, `ON_TOOL_CALL`, `ON_ERROR`, `ON_ESCALATION`, `SESSION_START`, `SESSION_END`, `PRE_COMPACT`
- Priority-based execution (higher priority executes first)
- Error isolation — one hook failure doesn't block others
- Built-in hooks for common patterns:
  - `session_persistence_hook`: Saves session summaries on SESSION_END
  - `cost_guard_hook`: Checks budget before execution
  - `audit_trail_hook`: Logs all tool calls for compliance
  - `escalation_hook`: Notifies on low confidence (< 0.7)
  - `context_loader_hook`: Pre-fetches knowledge on SESSION_START

**Usage**:
```python
from src.hooks.engine import HookEngine, Hook, HookType, HookContext, create_default_hooks

# Create engine
engine = HookEngine()

# Register built-in hooks
for hook in create_default_hooks():
    engine.register(hook)

# Create custom hook
async def custom_hook(context: HookContext) -> None:
    if context.hook_type == HookType.POST_EXECUTE:
        print(f"Task completed: {context.task}")

engine.register(Hook(
    name="my_hook",
    hook_type=HookType.POST_EXECUTE,
    handler=custom_hook,
    priority=50,
))

# Fire hooks
context = HookContext(
    hook_type=HookType.SESSION_START,
    session_id="session_123",
    task="Process claim",
)
await engine.fire(HookType.SESSION_START, context)
```

**Integration Points**:
- `BaseAgent.execute()`: Fires PRE_EXECUTE, POST_EXECUTE, ON_ERROR hooks
- `BaseAgent._execute_tools()`: Fires ON_TOOL_CALL hook
- `SupervisorAgent.process_request()`: Fires SESSION_START, PRE_EXECUTE, POST_EXECUTE, ON_ESCALATION, SESSION_END hooks

### 2. Subagent Delegation (`src/agents/subagent.py`)

**Purpose**: Task decomposition via lightweight subagents, enabling parallel execution of subtasks.

**Key Classes**:
- `SubagentConfig`: Configuration template (model, tokens, temperature, tools, budget, timeout)
- `SubagentPool`: Manages subagent lifecycle
- `SubagentResult`: Result with output, tokens, cost, latency

**Features**:
- Spawn lightweight agents for specific subtasks
- Max 3 concurrent subagents per parent (configurable)
- Cost rolls up to parent's budget
- Timeout handling (default 30s per subtask)
- Parallel task execution via `spawn_parallel()`
- Pre-configured templates:
  - `DATA_FETCHER_CONFIG`: Haiku, cheap, retrieves data
  - `ANALYZER_CONFIG`: Sonnet, moderate cost, analyzes
  - `VALIDATOR_CONFIG`: Haiku, cheap, validates outputs
  - `SUMMARIZER_CONFIG`: Haiku, cheap, compresses text

**Usage**:
```python
from src.agents.subagent import SubagentPool, DATA_FETCHER_CONFIG

pool = SubagentPool(model_router, tool_registry)

# Spawn single subagent
result = await pool.spawn(
    parent_agent_id="claims_agent",
    config=DATA_FETCHER_CONFIG,
    task="Fetch claim details for CLM-5000",
)
print(f"Output: {result.output}")
print(f"Cost: ${result.cost:.2f}")

# Spawn multiple in parallel
tasks = [
    (DATA_FETCHER_CONFIG, "Fetch claim data"),
    (ANALYZER_CONFIG, "Analyze medical records"),
    (VALIDATOR_CONFIG, "Validate results"),
]
results = await pool.spawn_parallel("claims_agent", tasks)
```

**Integration in BaseAgent**:
```python
# In BaseAgent config:
config = {
    "can_spawn_subagents": True,
    # ... other config
}

# Call from agent:
if self.can_spawn_subagents:
    result = await self.spawn_subagent(config, task)
```

### 3. Evaluation Framework (`src/evals/runner.py`)

**Purpose**: Comprehensive eval suite for agent orchestration quality assessment and A/B comparison.

**Key Classes**:
- `EvalSuite`: Registry and runner for evaluation functions
- `EvalResult`: Results from single evaluator
- `EvalSuiteResult`: Aggregated results from all evaluators

**Built-in Evaluators**:
- `semantic_similarity_evaluator`: Embedding-based similarity (pass ≥0.8)
- `hallucination_detector`: Flags claims not grounded in context
- `routing_accuracy`: Checks if correct agent was selected
- `cost_efficiency_evaluator`: Pass if cost ≤90% of budget
- `latency_compliance`: Pass if latency ≤ SLA
- `guardrail_effectiveness`: Measures false positive rate

**Usage**:
```python
from src.evals.runner import (
    EvalSuite,
    semantic_similarity_evaluator,
    hallucination_detector,
)

suite = EvalSuite()

# Register evaluators with weights
suite.add_evaluator(
    name="semantic_similarity",
    fn=semantic_similarity_evaluator,
    weight=1.0,
)

# Create test dataset
dataset = [
    {
        "input": "What's the status?",
        "expected": "Claim is approved",
        "metadata": {"cost": 0.05},
    },
]

# Mock agent function
async def my_agent(user_input: str) -> str:
    return "Claim is approved and pending payment"

# Run evaluators
results = await suite.run(dataset, my_agent)

# Compare two variants
results_a = await suite.run(dataset, agent_v1)
results_b = await suite.run(dataset, agent_v2)
comparison = await suite.compare(results_a, results_b)

# Generate report
report = suite.generate_report(results)
print(report)
```

### 4. Memory Consolidation (`src/memory/consolidation.py`)

**Purpose**: Compress long sessions into reusable knowledge for organizational learning.

**Key Classes**:
- `MemoryConsolidator`: Manages consolidation, archival, and pattern extraction
- `SessionSummary`: Compressed session representation
- `PatternInsight`: Recurring pattern identified across sessions

**Features**:
- Summarize sessions into key facts for efficient storage
- Archive old conversations (>90 days) to cold storage
- Find similar sessions via semantic search
- Extract recurring patterns for organizational learning

**Usage**:
```python
from src.memory.consolidation import MemoryConsolidator

consolidator = MemoryConsolidator(
    db_manager=db_manager,
    session_store=session_store,
    knowledge_store=knowledge_store,
)

# Consolidate a long session
summary = await consolidator.consolidate_session("session_123")
print(f"Key facts: {summary.key_facts}")
print(f"Agents used: {summary.agents_used}")
print(f"Cost: ${summary.total_cost:.2f}")

# Archive old conversations
archived = await consolidator.archive_old_conversations(days=90)
print(f"Archived {archived} conversations")

# Find similar sessions
similar = await consolidator.find_similar_sessions(
    query="Process auto insurance claim",
    limit=5,
)

# Extract patterns
patterns = await consolidator.extract_patterns(sample_size=100)
for pattern in patterns:
    print(f"{pattern.description}: {pattern.frequency} occurrences")
```

## Updated Components

### BaseAgent (`src/agents/base.py`)

**Changes**:
- Added `hook_engine: HookEngine` parameter
- Added `subagent_pool` parameter
- Added `can_spawn_subagents: bool` config flag
- Updated `execute()` to fire hooks at key points
- Updated `_execute_tools()` to fire ON_TOOL_CALL hooks
- Added `spawn_subagent()` method for task delegation

**Execution Flow**:
```
1. PRE_EXECUTE hook
2. Circuit breaker check
3. Budget check
4. Build prompt
5. Call LLM
6. Tool calls:
   - Fire ON_TOOL_CALL hook
   - Execute tool
7. POST_EXECUTE hook (on success)
8. ON_ERROR hook (on failure)
9. Track metrics
```

### SupervisorAgent (`src/orchestrator/supervisor.py`)

**Changes**:
- Added `hook_engine: HookEngine` parameter
- Added `subagent_pool` parameter
- Updated `process_request()` to fire hooks at all stages

**Orchestration Flow**:
```
1. SESSION_START hook
2. Intent classification
3. Pre-execution guardrails
4. PRE_EXECUTE hook
5. Context retrieval
6. Task decomposition (subagent-aware)
7. Agent routing & execution
8. Post-execution guardrails
9. POST_EXECUTE hook (or ON_ESCALATION if blocked)
10. SESSION_END hook
11. Store results in memory
```

## Integration with Existing Code

### Adding Hooks to Your Application

```python
from src.hooks.engine import HookEngine, create_default_hooks
from src.agents.subagent import SubagentPool
from src.orchestrator.supervisor import SupervisorAgent

# Initialize hook engine with defaults
hook_engine = HookEngine()
for hook in create_default_hooks():
    hook_engine.register(hook)

# Initialize subagent pool
subagent_pool = SubagentPool(
    model_router=model_router,
    tool_registry=tool_registry,
)

# Pass to supervisor
supervisor = SupervisorAgent(
    model_router=model_router,
    session_store=session_store,
    conversation_store=conversation_store,
    knowledge_store=knowledge_store,
    db_manager=db_manager,
    hook_engine=hook_engine,
    subagent_pool=subagent_pool,
)

await supervisor.initialize()
```

### Registering Custom Hooks

```python
from src.hooks.engine import Hook, HookType, HookContext

async def custom_logging_hook(context: HookContext) -> None:
    if context.hook_type == HookType.POST_EXECUTE:
        print(f"Completed: {context.task[:50]}")

hook_engine.register(Hook(
    name="custom_logging",
    hook_type=HookType.POST_EXECUTE,
    handler=custom_logging_hook,
    priority=50,
))
```

### Enabling Subagent Spawning

```python
# In agent config:
config = {
    "can_spawn_subagents": True,
    "max_tokens_per_task": 4096,
    "budget_limit_daily": 200.0,
    "tools": ["database_query", "document_search"],
}

# In agent code:
result = await self.spawn_subagent(
    config=DATA_FETCHER_CONFIG,
    task="Fetch claim documents",
)
```

### Running Evaluations

```python
from src.evals.runner import EvalSuite, semantic_similarity_evaluator

suite = EvalSuite()
suite.add_evaluator("similarity", semantic_similarity_evaluator)

results = await suite.run(dataset, agent_fn)
print(suite.generate_report(results))
```

## Performance Considerations

### Hook Overhead
- Hooks are async and execute in parallel where possible
- Error isolation prevents cascade failures
- Typical overhead: 10-50ms per hook execution

### Subagent Costs
- Cost rolls up to parent budget
- Concurrent subagents limited to prevent runaway costs
- Each subagent has individual timeout (default 30s)

### Memory Consolidation
- Consolidation is async and can run in background
- Archival doesn't block hot storage queries
- Pattern extraction runs on sampled sessions

## Examples

See `src/examples/advanced_orchestration.py` for comprehensive examples:
1. Hook system usage
2. Subagent spawning and parallel execution
3. Evaluation suite setup and reporting
4. Memory consolidation workflows
5. Full orchestration integration

Run examples:
```bash
python -m src.examples.advanced_orchestration
```

## Backward Compatibility

All changes are backward compatible:
- Hook engine is optional (defaults to empty engine)
- Subagent pool is optional (agents work without it)
- Evaluation framework is standalone
- Memory consolidation is opt-in

Existing code continues to work without modifications.

## Best Practices

1. **Hooks**: Use for cross-cutting concerns (logging, compliance, escalation)
2. **Subagents**: Decompose complex tasks (data fetching, analysis, validation)
3. **Evaluation**: Run evals regularly to catch quality regressions
4. **Consolidation**: Periodically consolidate long sessions to optimize storage
5. **Error Handling**: Rely on hook error isolation to prevent cascade failures

## Architecture Diagram

```
┌─────────────────────────────────────────────┐
│        SupervisorAgent                      │
├─────────────────────────────────────────────┤
│ • Intent routing                            │
│ • Task decomposition (subagent-aware)       │
│ • Guardrails (pre/post)                     │
│ • Hook firing (SESSION*, PRE/POST_EXECUTE) │
└────┬──────────────────────────┬─────────────┘
     │                          │
     ▼                          ▼
┌─────────────────┐     ┌──────────────────┐
│  BaseAgent      │     │  SubagentPool    │
├─────────────────┤     ├──────────────────┤
│ • Domain logic  │     │ • Lightweight    │
│ • Tool calls    │     │   task agents    │
│ • Hooks         │     │ • Concurrency    │
│ • Cost tracking │     │   limits         │
│ • Circuit break │     │ • Timeout mgmt   │
└────┬────────────┘     └──────────────────┘
     │
     ▼
┌──────────────────────────────────────────────┐
│       HookEngine                             │
├──────────────────────────────────────────────┤
│ • PRE_EXECUTE, POST_EXECUTE                  │
│ • ON_TOOL_CALL, ON_ERROR                     │
│ • ON_ESCALATION, SESSION_START/END           │
│ • Error isolation, priority-based execution  │
└──────────────────────────────────────────────┘

┌──────────────────────────────────────────────┐
│       EvalSuite                              │
├──────────────────────────────────────────────┤
│ • Semantic similarity evaluator              │
│ • Hallucination detector                     │
│ • Routing accuracy                           │
│ • Cost efficiency & latency compliance       │
│ • A/B comparison                             │
└──────────────────────────────────────────────┘

┌──────────────────────────────────────────────┐
│       MemoryConsolidator                     │
├──────────────────────────────────────────────┤
│ • Session summarization                      │
│ • Archive old conversations                  │
│ • Similar session search                     │
│ • Pattern extraction                         │
└──────────────────────────────────────────────┘
```

## Support

For questions or issues, refer to the example file or inline documentation in the source files.
