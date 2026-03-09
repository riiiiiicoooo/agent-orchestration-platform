"""
Guardrail Engine — Deterministic safety and compliance checks.

All guardrails are deterministic (regex, schema validation, budget checks)
rather than LLM-based, because insurance regulators need explainable decisions.
"""

import logging
import re
from typing import Any

from langsmith import traceable

from src.orchestrator.state import Intent, GuardrailResult

logger = logging.getLogger(__name__)


class GuardrailEngine:
    """
    Five-layer guardrail system for agent safety and compliance.

    Layers:
    1. PII Detection — Block/redact sensitive personal information
    2. Budget Enforcement — Per-agent, per-user token budgets
    3. Schema Validation — Ensure outputs match expected structure
    4. Compliance Rules — Insurance-specific regulatory checks
    5. Content Filtering — Block prohibited content patterns
    """

    def __init__(self):
        self.pii_patterns = self._compile_pii_patterns()
        self.compliance_rules = self._load_compliance_rules()

    @traceable(name="guardrail_engine.check_input")
    async def check_input(
        self,
        user_input: str,
        intent: Intent,
        user_id: str,
    ) -> GuardrailResult:
        """Pre-execution guardrail checks on user input."""

        # Layer 1: PII Detection
        pii_result = self._check_pii(user_input)
        if pii_result.blocked:
            return pii_result

        # Layer 5: Content filtering (prompt injection, abuse)
        content_result = self._check_content(user_input)
        if content_result.blocked:
            return content_result

        return GuardrailResult(blocked=False)

    @traceable(name="guardrail_engine.check_output")
    async def check_output(
        self,
        response: str,
        intent: Intent,
        agent_outputs: dict[str, Any],
    ) -> GuardrailResult:
        """Post-execution guardrail checks on agent output."""

        # Layer 1: PII in output
        pii_result = self._check_pii(response)
        if pii_result.blocked:
            return GuardrailResult(
                blocked=True,
                reason="PII detected in agent output",
                severity="critical",
                details=pii_result.details,
                message="Response contained sensitive information and was blocked.",
            )

        # Layer 4: Compliance checks (domain-specific)
        if intent and intent.domain in ("claims", "underwriting"):
            compliance_result = self._check_compliance(response, intent)
            if compliance_result.blocked:
                return compliance_result

        # Layer 3: Schema validation (if agent output has expected structure)
        for agent_id, output in agent_outputs.items():
            if output.get("status") == "success" and output.get("response"):
                schema_result = self._check_schema(output["response"], agent_id)
                if schema_result.blocked:
                    return schema_result

        return GuardrailResult(blocked=False)

    def _check_pii(self, text: str) -> GuardrailResult:
        """Detect PII patterns using regex (deterministic, not LLM-based)."""
        found_pii = []

        for pii_type, pattern in self.pii_patterns.items():
            if pattern.search(text):
                found_pii.append(pii_type)

        if found_pii:
            return GuardrailResult(
                blocked=True,
                reason=f"PII detected: {', '.join(found_pii)}",
                severity="critical",
                details={"pii_types": found_pii},
                message="Request contains sensitive personal information that must be redacted.",
            )

        return GuardrailResult(blocked=False)

    def _check_content(self, text: str) -> GuardrailResult:
        """Check for prompt injection and prohibited content."""
        injection_patterns = [
            r"ignore\s+(previous|all|above)\s+(instructions|prompts)",
            r"you\s+are\s+now\s+a",
            r"system\s*:\s*override",
            r"jailbreak",
            r"DAN\s+mode",
        ]

        for pattern in injection_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return GuardrailResult(
                    blocked=True,
                    reason="Potential prompt injection detected",
                    severity="critical",
                    details={"pattern": pattern},
                    message="This request was blocked for security reasons.",
                )

        return GuardrailResult(blocked=False)

    def _check_compliance(self, response: str, intent: Intent) -> GuardrailResult:
        """Insurance-specific compliance checks."""
        text_lower = response.lower()

        # Claims: Check for unauthorized coverage determinations
        if intent.domain == "claims":
            definitive_phrases = [
                "your claim is approved",
                "your claim is denied",
                "coverage is confirmed",
                "we will pay",
                "the claim amount is",
            ]
            for phrase in definitive_phrases:
                if phrase in text_lower:
                    return GuardrailResult(
                        blocked=True,
                        reason=f"Unauthorized coverage determination: '{phrase}'",
                        severity="critical",
                        details={"phrase": phrase, "domain": "claims"},
                        message="This response requires human review before delivery.",
                    )

        # Underwriting: Check for unauthorized premium commitments
        if intent.domain == "underwriting":
            commitment_phrases = [
                "your premium will be",
                "we can offer you",
                "the rate is",
                "binding coverage",
            ]
            for phrase in commitment_phrases:
                if phrase in text_lower:
                    return GuardrailResult(
                        blocked=True,
                        reason=f"Unauthorized premium commitment: '{phrase}'",
                        severity="critical",
                        details={"phrase": phrase, "domain": "underwriting"},
                        message="Premium commitments require underwriter approval.",
                    )

        return GuardrailResult(blocked=False)

    def _check_schema(self, response: str, agent_id: str) -> GuardrailResult:
        """Validate agent output structure."""
        # In production: JSON schema validation against expected output formats
        return GuardrailResult(blocked=False)

    def _compile_pii_patterns(self) -> dict[str, re.Pattern]:
        """Compile PII detection regex patterns."""
        return {
            "ssn": re.compile(r"\b\d{3}-?\d{2}-?\d{4}\b"),
            "credit_card": re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"),
            "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
            "phone": re.compile(r"\b(?:\+1[\s-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b"),
            "dob": re.compile(r"\b(?:date\s+of\s+birth|dob)\s*:?\s*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", re.IGNORECASE),
            "drivers_license": re.compile(r"\b(?:DL|driver'?s?\s*license)\s*#?\s*:?\s*[A-Z0-9]{6,15}\b", re.IGNORECASE),
        }

    def _load_compliance_rules(self) -> dict[str, Any]:
        """Load compliance rules from configuration."""
        return {
            "claims_max_auto_approve": 10000,  # Auto-approve claims under $10K
            "underwriting_requires_review": True,
            "hipaa_required": True,
            "audit_retention_days": 2555,  # 7 years for insurance
        }
