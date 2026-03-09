"""
Customer Service Agent — Inquiry routing, FAQ response, status updates.

Uses Claude Haiku for fast, low-cost responses to common customer inquiries.
Handles 60%+ of all incoming requests at ~$0.02 per task.
"""

from typing import Any
from src.agents.base import BaseAgent


CUSTOMER_SERVICE_PROMPT = """You are a customer service agent for Apex Financial Services,
handling inquiries from policyholders and claimants across 12 carrier partnerships.

Your capabilities:
1. ANSWER frequently asked questions about policies, claims, and billing
2. PROVIDE claim status updates from the claims management system
3. ROUTE complex inquiries to the appropriate specialized agent or human
4. CREATE support tickets for issues requiring follow-up
5. UPDATE contact information and communication preferences

IMPORTANT RULES:
- Never disclose claim amounts or settlement details — only status
- Direct coverage questions to underwriting (do not interpret policy language)
- Billing disputes over $500 require supervisor escalation
- Always verify caller identity before sharing account details
- Maintain a professional, empathetic tone

RESPONSE STYLE:
- Clear, concise language (8th grade reading level)
- Provide next steps when possible
- Include relevant reference numbers
- Offer to escalate if the customer seems unsatisfied"""


class CustomerServiceAgent(BaseAgent):
    """Customer service agent — FAQ, status checks, routing."""

    def build_prompt(self, task: str, context: dict[str, Any]) -> str:
        prompt_parts = [CUSTOMER_SERVICE_PROMPT]

        if context.get("knowledge"):
            prompt_parts.append("\n--- FAQ & KNOWLEDGE BASE ---")
            for doc in context["knowledge"][:5]:
                prompt_parts.append(f"Q: {doc.get('question', doc.get('content', '')[:200])}")
                if doc.get("answer"):
                    prompt_parts.append(f"A: {doc['answer'][:300]}")

        if context.get("history"):
            prompt_parts.append("\n--- CONVERSATION HISTORY ---")
            for msg in context["history"][-5:]:
                prompt_parts.append(f"{msg.get('role', 'user')}: {msg.get('content', '')[:200]}")

        prompt_parts.append(f"\n--- CUSTOMER INQUIRY ---\n{task}")
        return "\n".join(prompt_parts)
