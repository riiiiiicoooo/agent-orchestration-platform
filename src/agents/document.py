"""
Document Processing Agent — OCR extraction, classification, data normalization.

Uses Claude 3.5 Sonnet for document understanding with Azure Document Intelligence
as a fallback for complex scanned documents.
"""

from typing import Any
from src.agents.base import BaseAgent


DOCUMENT_PROCESSING_PROMPT = """You are a document processing specialist for Apex Financial Services,
handling insurance documents across claims, underwriting, and policy administration.

Your capabilities:
1. CLASSIFY documents by type (policy, endorsement, claim form, medical record, invoice, correspondence)
2. EXTRACT structured data from documents (dates, amounts, parties, coverage details)
3. NORMALIZE extracted data into standard schemas for downstream processing
4. VALIDATE extracted data against known patterns and business rules
5. FLAG documents requiring manual review (poor quality, ambiguous, incomplete)

DOCUMENT TYPES AND EXPECTED FIELDS:
- Policy Declaration: policy_number, effective_date, expiration_date, named_insured, limits, deductibles
- Claim Form: claim_number, date_of_loss, claimant, description, estimated_amount
- Medical Record: patient_name, provider, dates_of_service, diagnosis_codes, treatment_summary
- Invoice: vendor, date, amount, line_items, policy_reference
- Endorsement: endorsement_number, effective_date, changes_summary, premium_impact

IMPORTANT RULES:
- PII fields must be tagged for appropriate handling
- Medical records require HIPAA-compliant processing
- Confidence scores required for all extracted fields
- Documents with <80% extraction confidence should be flagged for human review
- Always preserve original document reference for audit trail"""


class DocumentProcessingAgent(BaseAgent):
    """Document processing agent — OCR, classification, extraction."""

    def build_prompt(self, task: str, context: dict[str, Any]) -> str:
        prompt_parts = [DOCUMENT_PROCESSING_PROMPT]

        if context.get("knowledge"):
            prompt_parts.append("\n--- DOCUMENT TEMPLATES & SCHEMAS ---")
            for doc in context["knowledge"][:3]:
                prompt_parts.append(f"[{doc.get('source', 'template')}]: {doc.get('content', '')[:500]}")

        if context.get("chain"):
            prompt_parts.append("\n--- PRIOR PROCESSING ---")
            for agent_id, output in context["chain"].items():
                prompt_parts.append(f"[{agent_id}]: {output.get('response', '')[:500]}")

        prompt_parts.append(f"\n--- DOCUMENT TASK ---\n{task}")
        return "\n".join(prompt_parts)
