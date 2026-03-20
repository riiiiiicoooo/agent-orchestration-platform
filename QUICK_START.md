# Quick Start — Using New Agent Orchestration Features

## 1. Hook System (5 minutes)

### Setup
```python
from src.hooks.engine import HookEngine, Hook, HookType, HookContext, create_default_hooks

# Create and initialize with defaults
engine = HookEngine()
for hook in create_default_hooks():
    engine.register(hook)
```

### Custom Hook
```python
async def my_custom_hook(context: HookContext) -> None:
    if context.hook_type == HookType.POST_EXECUTE:
        print(f"Task done: {context.task[:50]}")

engine.register(Hook(
    name="my_hook",
    hook_type=HookType.POST_EXECUTE,
    handler=my_custom_hook,
    priority=50,
))
```

### Fire Hooks
```python
context = HookContext(
    hook_type=HookType.SESSION_START,
    session_id="session_123",
    task="Process claim",
)
await engine.fire(HookType.SESSION_START, context)
```

---

## 2. Subagent Spawning (5 minutes)

### Setup
```python
from src.agents.subagent import SubagentPool, DATA_FETCHER_CONFIG, ANALYZER_CONFIG

pool = SubagentPool(
    model_router=model_router,
    tool_registry=tool_registry,
)
```

### Spawn Single Subagent
```python
result = await pool.spawn(
    parent_agent_id="claims_agent",
    config=DATA_FETCHER_CONFIG,
    task="Fetch claim CLM-5000 details",
)

print(f"Output: {result.output}")
print(f"Cost: ${result.cost:.2f}, Latency: {result.latency_ms:.0f}ms")
```

### Spawn in Parallel
```python
tasks = [
    (DATA_FETCHER_CONFIG, "Fetch claim data"),
    (ANALYZER_CONFIG, "Analyze medical records"),
    (ANALYZER_CONFIG, "Analyze claim history"),
]

results = await pool.spawn_parallel("claims_agent", tasks)
total_cost = sum(r.cost for r in results)
print(f"Total cost: ${total_cost:.2f}")
```

---

## 3. Evaluation Framework (5 minutes)

### Setup
```python
from src.evals.runner import EvalSuite, semantic_similarity_evaluator, hallucination_detector

suite = EvalSuite()
suite.add_evaluator("similarity", semantic_similarity_evaluator, weight=1.0)
suite.add_evaluator("hallucination", hallucination_detector, weight=1.0)
```

### Run Evaluation
```python
dataset = [
    {
        "input": "What's the status?",
        "expected": "Claim is approved",
        "metadata": {"cost": 0.05},
    },
]

async def my_agent(user_input: str) -> str:
    return "Claim is approved and pending payment"

results = await suite.run(dataset, my_agent)
```

### Generate Report
```python
report = suite.generate_report(results)
print(report)
```

### A/B Compare
```python
results_v1 = await suite.run(dataset, agent_v1)
results_v2 = await suite.run(dataset, agent_v2)
comparison = await suite.compare(results_v1, results_v2)
print(f"V2 improvement: {comparison['overall_pass_rate']['delta']:.1%}")
```

---

## 4. Memory Consolidation (5 minutes)

### Setup
```python
from src.memory.consolidation import MemoryConsolidator

consolidator = MemoryConsolidator(
    db_manager=db_manager,
    session_store=session_store,
    knowledge_store=knowledge_store,
)
```

### Consolidate Session
```python
summary = await consolidator.consolidate_session("session_123")
print(f"Key facts: {summary.key_facts}")
print(f"Agents used: {summary.agents_used}")
print(f"Cost: ${summary.total_cost:.2f}")
```

### Archive Old Data
```python
archived = await consolidator.archive_old_conversations(days=90)
print(f"Archived {archived} conversations")
```

### Find Similar Sessions
```python
similar = await consolidator.find_similar_sessions(
    query="Process auto insurance claim",
    limit=5,
)
for session in similar:
    print(f"- {session.session_id}: ${session.total_cost:.2f}")
```

### Extract Patterns
```python
patterns = await consolidator.extract_patterns(sample_size=100)
for pattern in patterns:
    print(f"{pattern.description} ({pattern.frequency} occurrences)")
    print(f"  Recommendation: {pattern.recommendation}")
```

---

## 5. Full Integration (10 minutes)

### Initialize Everything
```python
from src.hooks.engine import HookEngine, create_default_hooks
from src.agents.subagent import SubagentPool
from src.orchestrator.supervisor import SupervisorAgent

# 1. Hooks
hook_engine = HookEngine()
for hook in create_default_hooks():
    hook_engine.register(hook)

# 2. Subagents
subagent_pool = SubagentPool(model_router, tool_registry)

# 3. Supervisor (with hooks and subagents)
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

### Process Request (hooks fire automatically)
```python
# This will fire: SESSION_START → PRE_EXECUTE → POST_EXECUTE
result = await supervisor.process_request(
    user_input="Process claim CLM-5000",
    session_id="session_123",
    user_id="user_456",
)

print(f"Response: {result.response}")
print(f"Success: {result.success}")
```

### Custom Hook for Your Domain
```python
async def custom_business_logic_hook(context: HookContext) -> None:
    if context.hook_type == HookType.POST_EXECUTE:
        # Custom business metrics
        print(f"Task completed in session {context.session_id}")
        # Could trigger: webhook, Slack notification, database update, etc.

hook_engine.register(Hook(
    name="business_logic",
    hook_type=HookType.POST_EXECUTE,
    handler=custom_business_logic_hook,
    priority=40,
))
```

---

## Common Patterns

### Pattern 1: Decompose Complex Task
```python
# Use subagents for parallelizable work
tasks = [
    (DATA_FETCHER_CONFIG, "Fetch documents"),
    (ANALYZER_CONFIG, "Analyze documents"),
    (VALIDATOR_CONFIG, "Validate results"),
]
results = await pool.spawn_parallel("parent_agent", tasks)
```

### Pattern 2: Monitor Quality
```python
# Run evals after deployment
suite = EvalSuite()
suite.add_evaluator("semantic", semantic_similarity_evaluator)
results = await suite.run(test_dataset, agent_fn)
if results.overall_pass_rate < 0.90:
    print("Quality regression detected!")
```

### Pattern 3: Learn from History
```python
# Consolidate old sessions for organizational learning
patterns = await consolidator.extract_patterns(sample_size=100)
for pattern in patterns:
    if "high_cost" in pattern.pattern_id:
        print(f"Cost optimization opportunity: {pattern.recommendation}")
```

### Pattern 4: Audit Trail
```python
# Audit logging via hook
async def audit_hook(context: HookContext) -> None:
    if context.hook_type == HookType.ON_TOOL_CALL:
        log_to_audit_system(
            session=context.session_id,
            tool=context.tool_name,
            args=context.tool_args,
        )

hook_engine.register(Hook(
    name="audit_log",
    hook_type=HookType.ON_TOOL_CALL,
    handler=audit_hook,
    priority=99,
))
```

### Pattern 5: Cost Control
```python
# Cost guard hook prevents budget overruns
# This is enabled by default in create_default_hooks()
# Customize by adjusting hook priority or disabling

hook_engine.disable("cost_guard")  # Turn off if needed
hook_engine.enable("cost_guard")   # Turn back on
```

---

## Troubleshooting

### Hook Not Firing?
```python
# Check if hook is registered
hooks = engine._hooks[HookType.POST_EXECUTE]
print(f"Registered hooks: {[h.name for h in hooks]}")

# Check if hook is enabled
if not hook.enabled:
    engine.enable("my_hook")

# Check metrics
metrics = engine.get_metrics()
print(f"Hook calls: {metrics['my_hook']['calls']}")
```

### Subagent Timing Out?
```python
# Increase timeout in config
config = SubagentConfig(
    name="slow_agent",
    model="claude-3.5-sonnet",
    timeout_seconds=60,  # Increase from default 30
)

result = await pool.spawn("parent", config, task)
if not result.success:
    print(f"Error: {result.error}")
```

### Eval Passing But Quality Low?
```python
# Add more evaluators or adjust weights
suite.add_evaluator("hallucination", hallucination_detector, weight=2.0)
# Higher weight = more impact on score

# Generate detailed report to see failures
for evaluator_name, eval_result in results.evaluators.items():
    if eval_result.failures:
        print(f"\n{evaluator_name} failures:")
        for failure in eval_result.failures[:5]:
            print(f"  - {failure}")
```

---

## See Also

- **UPGRADE_GUIDE.md**: Comprehensive integration guide with architecture diagrams
- **IMPLEMENTATION_SUMMARY.md**: Detailed technical summary of all changes
- **src/examples/advanced_orchestration.py**: Full working examples

---

## Key Takeaways

1. **Hooks** = Cross-cutting concerns (logging, compliance, escalation)
2. **Subagents** = Task decomposition (parallel execution, cost control)
3. **Evals** = Quality monitoring (regression detection, A/B testing)
4. **Consolidation** = Organizational learning (patterns, optimization)

All are **optional**, **backward compatible**, and **production-ready**.
