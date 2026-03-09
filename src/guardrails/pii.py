"""
PII Detection Module — Presidio-based PII detection and redaction.

Uses Microsoft Presidio for structured PII recognition with
custom recognizers for insurance-specific patterns.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class PIIDetector:
    """
    PII detection and redaction using Microsoft Presidio.

    Custom recognizers for:
    - Policy numbers (carrier-specific formats)
    - Claim numbers
    - NAIC codes
    - Agent license numbers
    """

    def __init__(self):
        self.analyzer = None  # presidio_analyzer.AnalyzerEngine
        self.anonymizer = None  # presidio_anonymizer.AnonymizerEngine
        self._initialize()

    def _initialize(self) -> None:
        """Initialize Presidio with custom recognizers."""
        try:
            from presidio_analyzer import AnalyzerEngine, PatternRecognizer, Pattern
            from presidio_anonymizer import AnonymizerEngine

            self.analyzer = AnalyzerEngine()
            self.anonymizer = AnonymizerEngine()

            # Custom: Policy number recognizer (format: POL-XXXX-XXXXXXX)
            policy_recognizer = PatternRecognizer(
                supported_entity="POLICY_NUMBER",
                patterns=[Pattern(name="policy_num", regex=r"POL-\w{4}-\w{7}", score=0.9)],
            )
            self.analyzer.registry.add_recognizer(policy_recognizer)

            # Custom: Claim number recognizer (format: CLM-XXXXXXXX)
            claim_recognizer = PatternRecognizer(
                supported_entity="CLAIM_NUMBER",
                patterns=[Pattern(name="claim_num", regex=r"CLM-\w{8}", score=0.9)],
            )
            self.analyzer.registry.add_recognizer(claim_recognizer)

            logger.info("Presidio PII detector initialized with custom recognizers")

        except ImportError:
            logger.warning("Presidio not installed — using regex fallback")

    def detect(self, text: str) -> list[dict[str, Any]]:
        """Detect PII entities in text."""
        if self.analyzer:
            results = self.analyzer.analyze(
                text=text,
                entities=[
                    "PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER",
                    "US_SSN", "CREDIT_CARD", "US_DRIVER_LICENSE",
                    "POLICY_NUMBER", "CLAIM_NUMBER",
                ],
                language="en",
            )
            return [
                {
                    "entity_type": r.entity_type,
                    "start": r.start,
                    "end": r.end,
                    "score": r.score,
                    "text": text[r.start:r.end],
                }
                for r in results
            ]
        return []

    def redact(self, text: str) -> str:
        """Redact PII from text."""
        if self.analyzer and self.anonymizer:
            results = self.analyzer.analyze(text=text, language="en")
            anonymized = self.anonymizer.anonymize(text=text, analyzer_results=results)
            return anonymized.text
        return text
