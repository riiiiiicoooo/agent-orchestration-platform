"""
Intent Router — Fast intent classification for request routing.

Uses Claude Haiku for sub-200ms classification of incoming requests
into domain, complexity, and target agent(s).
"""

import logging
from typing import Any

from langsmith import traceable

from src.orchestrator.state import Intent
from src.providers.router import ModelRouter

logger = logging.getLogger(__name__)

# Intent classification prompt — optimized for Haiku speed
CLASSIFICATION_PROMPT = """You are an intent classifier for an insurance TPA's agent orchestration system.

Classify the user's request into exactly ONE domain and determine complexity.

DOMAINS:
- claims: Claim filing, status checks, damage assessment, coverage verification
- underwriting: Risk assessment, policy analysis, premium calculation, renewal review
- customer_service: General inquiries, FAQ, account status, billing questions
- document: Document upload, OCR, classification, data extraction
- analytics: Reports, trends, KPIs, performance metrics, comparisons

COMPLEXITY:
- simple: Single agent can handle (80% of requests)
- chain: Sequential agents needed (e.g., document → claims)
- parallel: Independent agents needed (e.g., claims + analytics)

Respond in JSON:
{
  "domain": "<domain>",
  "complexity": "<complexity>",
  "target_agents": ["<agent_id>", ...],
  "confidence": <0.0-1.0>,
  "requires_human_review": <true/false>
}

Rules:
- Coverage determinations ALWAYS require human_review=true
- Claim amounts >$50K require human_review=true
- Policy changes require human_review=true
- Simple FAQ/status checks never require human_review"""


COST_ESTIMATES = {
    "claims": 0.08,
    "underwriting": 0.14,
    "customer_service": 0.02,
    "document": 0.11,
    "analytics": 0.16,
}


class IntentRouter:
    """Fast intent classification using Claude Haiku."""

    def __init__(self, model_router: ModelRouter):
        self.model_router = model_router

    @traceable(name="intent_router.classify")
    async def classify(
        self,
        user_input: str,
        session_context: dict[str, Any] | None = None,
    ) -> Intent:
        """
        Classify user intent using Haiku for speed (<200ms target).

        Falls back to rule-based classification if LLM call fails.
        """
        try:
            # Use Haiku for fast classification
            response = await self.model_router.classify(
                prompt=CLASSIFICATION_PROMPT,
                user_input=user_input,
                session_context=session_context or {},
            )

            # Parse structured response
            import json
            parsed = json.loads(response)

            # Estimate cost based on target agents
            estimated_cost = sum(
                COST_ESTIMATES.get(agent_id, 0.10)
                for agent_id in parsed["target_agents"]
            )

            return Intent(
                domain=parsed["domain"],
                complexity=parsed["complexity"],
                target_agents=parsed["target_agents"],
                confidence=parsed["confidence"],
                requires_human_review=parsed["requires_human_review"],
                estimated_cost=estimated_cost,
            )

        except Exception as e:
            logger.warning("LLM classification failed, using rule-based fallback: %s", e)
            return self._rule_based_classify(user_input)

    def _rule_based_classify(self, user_input: str) -> Intent:
        """Rule-based fallback classification using keyword matching."""
        text = user_input.lower()

        # Simple keyword-based routing
        if any(kw in text for kw in ["claim", "damage", "loss", "incident", "accident"]):
            return Intent(
                domain="claims",
                complexity="simple",
                target_agents=["claims"],
                confidence=0.7,
                requires_human_review=False,
                estimated_cost=COST_ESTIMATES["claims"],
            )
        elif any(kw in text for kw in ["underwrite", "risk", "premium", "policy", "renewal"]):
            return Intent(
                domain="underwriting",
                complexity="simple",
                target_agents=["underwriting"],
                confidence=0.7,
                requires_human_review=True,  # Conservative for underwriting
                estimated_cost=COST_ESTIMATES["underwriting"],
            )
        elif any(kw in text for kw in ["document", "upload", "scan", "extract", "ocr"]):
            return Intent(
                domain="document",
                complexity="simple",
                target_agents=["document"],
                confidence=0.7,
                requires_human_review=False,
                estimated_cost=COST_ESTIMATES["document"],
            )
        elif any(kw in text for kw in ["report", "analytics", "trend", "metric", "dashboard"]):
            return Intent(
                domain="analytics",
                complexity="simple",
                target_agents=["analytics"],
                confidence=0.7,
                requires_human_review=False,
                estimated_cost=COST_ESTIMATES["analytics"],
            )
        else:
            return Intent(
                domain="customer_service",
                complexity="simple",
                target_agents=["customer_service"],
                confidence=0.5,
                requires_human_review=False,
                estimated_cost=COST_ESTIMATES["customer_service"],
            )
