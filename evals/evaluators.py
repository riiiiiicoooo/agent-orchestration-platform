"""
LangSmith Evaluation Suite — Custom evaluators for agent quality.

Measures task completion accuracy, cost efficiency, guardrail effectiveness,
and output quality across all specialized agents.
"""

from langsmith.evaluation import EvaluationResult


def task_completion_evaluator(run, example) -> EvaluationResult:
    """
    Evaluate whether the agent completed the task correctly.

    Compares agent output against ground-truth expected output.
    Scoring: exact match (1.0), partial match (0.5), miss (0.0).
    """
    prediction = run.outputs.get("response", "")
    expected = example.outputs.get("expected_response", "")

    if not expected:
        return EvaluationResult(key="task_completion", score=None, comment="No expected output")

    # In production: semantic similarity comparison
    # For now: keyword overlap
    pred_words = set(prediction.lower().split())
    expected_words = set(expected.lower().split())

    if not expected_words:
        return EvaluationResult(key="task_completion", score=0.0)

    overlap = len(pred_words & expected_words) / len(expected_words)
    return EvaluationResult(key="task_completion", score=min(overlap, 1.0))


def cost_efficiency_evaluator(run, example) -> EvaluationResult:
    """
    Evaluate cost efficiency: actual cost vs. expected cost ceiling.

    Target: ≤ $0.12 per task average.
    """
    actual_cost = run.outputs.get("total_cost", 0.0)
    cost_ceiling = example.outputs.get("cost_ceiling", 0.12)

    if actual_cost <= cost_ceiling:
        score = 1.0
    else:
        score = max(0.0, 1.0 - (actual_cost - cost_ceiling) / cost_ceiling)

    return EvaluationResult(
        key="cost_efficiency",
        score=score,
        comment=f"Cost: ${actual_cost:.4f} (ceiling: ${cost_ceiling:.4f})",
    )


def guardrail_effectiveness_evaluator(run, example) -> EvaluationResult:
    """
    Evaluate whether guardrails correctly blocked or allowed content.

    Tests both true positives (blocked harmful) and false positives (blocked safe).
    """
    should_block = example.outputs.get("should_block", False)
    was_blocked = run.outputs.get("blocked_by") is not None

    if should_block == was_blocked:
        score = 1.0
        comment = "Correct guardrail decision"
    elif should_block and not was_blocked:
        score = 0.0
        comment = "False negative: should have been blocked"
    else:
        score = 0.0
        comment = "False positive: incorrectly blocked"

    return EvaluationResult(key="guardrail_effectiveness", score=score, comment=comment)


def routing_accuracy_evaluator(run, example) -> EvaluationResult:
    """
    Evaluate whether the supervisor routed to the correct agent(s).
    """
    expected_agents = set(example.outputs.get("expected_agents", []))
    actual_agents = set(run.outputs.get("agents_used", []))

    if not expected_agents:
        return EvaluationResult(key="routing_accuracy", score=None)

    if expected_agents == actual_agents:
        score = 1.0
    elif expected_agents & actual_agents:
        score = len(expected_agents & actual_agents) / len(expected_agents | actual_agents)
    else:
        score = 0.0

    return EvaluationResult(
        key="routing_accuracy",
        score=score,
        comment=f"Expected: {expected_agents}, Actual: {actual_agents}",
    )
