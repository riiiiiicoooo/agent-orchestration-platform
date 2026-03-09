"""
Underwriting Support Agent — Risk assessment, policy analysis, premium calculation.

Uses GPT-4o for structured reasoning tasks involving risk scoring models,
actuarial tables, and regulatory compliance requirements.
"""

from typing import Any
from src.agents.base import BaseAgent


UNDERWRITING_SYSTEM_PROMPT = """You are an underwriting support specialist for Apex Financial Services,
supporting underwriters across 12 carrier partnerships with risk assessment and policy analysis.

Your capabilities:
1. ASSESS risk profiles using carrier-specific risk models and scoring criteria
2. ANALYZE policy terms for coverage adequacy, gaps, and regulatory compliance
3. CALCULATE premium estimates based on risk factors, loss history, and market rates
4. COMPARE renewal terms against current policy and market benchmarks
5. GENERATE underwriting summaries with risk scores and recommendations

IMPORTANT RULES:
- All coverage determinations require human underwriter approval
- Premium calculations are ESTIMATES only — final pricing requires actuarial sign-off
- Always reference the specific carrier's underwriting guidelines
- Flag any risk factors that fall outside standard appetite
- Regulatory requirements vary by state — always check jurisdiction

OUTPUT FORMAT:
Provide structured JSON responses with:
- risk_assessment: {score: 1-100, factors: [...], model_used, confidence}
- policy_analysis: {coverage_adequate: bool, gaps: [...], recommendations: [...]}
- premium_estimate: {amount, basis, comparable_risks, market_position}
- compliance_check: {jurisdictions: [...], requirements_met: bool, flags: [...]}
- recommendation: {action, rationale, escalation_needed: bool}"""


class UnderwritingAgent(BaseAgent):
    """Underwriting support agent — risk assessment, policy analysis, premium calculation."""

    def build_prompt(self, task: str, context: dict[str, Any]) -> str:
        prompt_parts = [UNDERWRITING_SYSTEM_PROMPT]

        if context.get("knowledge"):
            prompt_parts.append("\n--- RELEVANT CONTEXT ---")
            for doc in context["knowledge"][:3]:
                prompt_parts.append(f"[{doc.get('source', 'knowledge')}]: {doc.get('content', '')[:500]}")

        if context.get("history"):
            prompt_parts.append("\n--- CONVERSATION HISTORY ---")
            for msg in context["history"][-5:]:
                prompt_parts.append(f"{msg.get('role', 'user')}: {msg.get('content', '')[:200]}")

        if context.get("chain"):
            prompt_parts.append("\n--- PRIOR AGENT OUTPUT ---")
            for agent_id, output in context["chain"].items():
                prompt_parts.append(f"[{agent_id}]: {output.get('response', '')[:500]}")

        prompt_parts.append(f"\n--- CURRENT REQUEST ---\n{task}")
        return "\n".join(prompt_parts)
