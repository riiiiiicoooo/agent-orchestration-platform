"""
Claims Processing Agent — Intake classification, damage estimation, coverage verification.

Handles the full claims lifecycle from first notice of loss through
coverage determination. Uses Claude 3.5 Sonnet for document analysis
and structured data extraction.
"""

from typing import Any
from src.agents.base import BaseAgent


CLAIMS_SYSTEM_PROMPT = """You are a claims processing specialist for Apex Financial Services,
a third-party administrator managing claims across 12 insurance carrier partnerships.

Your capabilities:
1. CLASSIFY incoming claims by type (property, casualty, specialty, auto, workers comp)
2. ESTIMATE damage based on description, photos, and comparable claims
3. VERIFY coverage against policy terms using the policy database
4. EXTRACT structured data from claim documents (dates, amounts, parties, descriptions)
5. FLAG anomalies that may indicate fraud or require special handling

IMPORTANT RULES:
- Never make final coverage determinations — flag for human review
- Always cite the specific policy section when referencing coverage
- For claims >$50K, always recommend senior adjuster review
- PII must be handled according to data classification policy
- Include confidence scores with all estimates

OUTPUT FORMAT:
Provide structured JSON responses with:
- claim_classification: {type, subtype, severity, confidence}
- damage_estimate: {amount_low, amount_high, basis, comparable_claims}
- coverage_analysis: {covered: bool, sections: [...], exclusions: [...], confidence}
- next_steps: [{action, assignee, priority, deadline}]
- flags: [{type, description, severity}]"""


class ClaimsAgent(BaseAgent):
    """Claims processing agent — intake, estimation, coverage verification."""

    def build_prompt(self, task: str, context: dict[str, Any]) -> str:
        """Build claims-specific prompt with policy context."""
        prompt_parts = [CLAIMS_SYSTEM_PROMPT]

        # Add relevant knowledge (resolved claims, policy excerpts)
        if context.get("knowledge"):
            prompt_parts.append("\n--- RELEVANT CONTEXT ---")
            for doc in context["knowledge"][:3]:
                prompt_parts.append(f"[{doc.get('source', 'knowledge')}]: {doc.get('content', '')[:500]}")

        # Add conversation history for multi-turn claims
        if context.get("history"):
            prompt_parts.append("\n--- CONVERSATION HISTORY ---")
            for msg in context["history"][-5:]:
                role = msg.get("role", "user")
                content = msg.get("content", "")[:200]
                prompt_parts.append(f"{role}: {content}")

        # Add chain context (if document processing ran first)
        if context.get("chain"):
            prompt_parts.append("\n--- PRIOR AGENT OUTPUT ---")
            for agent_id, output in context["chain"].items():
                prompt_parts.append(f"[{agent_id}]: {output.get('response', '')[:500]}")

        prompt_parts.append(f"\n--- CURRENT REQUEST ---\n{task}")

        return "\n".join(prompt_parts)
