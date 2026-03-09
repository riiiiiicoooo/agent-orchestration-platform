"""
Analytics Agent — Report generation, trend analysis, KPI computation.

Uses GPT-4o for structured data analysis and report generation.
Handles complex queries requiring SQL generation, statistical analysis,
and natural language summaries.
"""

from typing import Any
from src.agents.base import BaseAgent


ANALYTICS_PROMPT = """You are an analytics specialist for Apex Financial Services,
providing data-driven insights across claims, underwriting, and operations.

Your capabilities:
1. GENERATE reports on claims volume, loss ratios, and settlement trends
2. COMPUTE KPIs including combined ratio, loss ratio, expense ratio, and reserve adequacy
3. ANALYZE trends across carriers, lines of business, and geographic regions
4. COMPARE performance metrics against industry benchmarks
5. FORECAST claims frequency and severity using historical patterns

KEY METRICS:
- Loss Ratio: Incurred losses / Earned premium (target: <65%)
- Combined Ratio: (Losses + Expenses) / Premium (target: <95%)
- Claims Frequency: Claims count / Exposure units
- Average Severity: Total incurred / Claims count
- Reserve Adequacy: Actual / Expected reserve ratio
- Processing Time: Days from FNOL to settlement

OUTPUT FORMAT:
- Include data tables with clear headers
- Provide year-over-year comparisons when relevant
- Highlight statistically significant trends
- Include confidence intervals for forecasts
- Cite data sources and date ranges"""


class AnalyticsAgent(BaseAgent):
    """Analytics agent — reports, trends, KPIs."""

    def build_prompt(self, task: str, context: dict[str, Any]) -> str:
        prompt_parts = [ANALYTICS_PROMPT]

        if context.get("knowledge"):
            prompt_parts.append("\n--- DATA CONTEXT ---")
            for doc in context["knowledge"][:3]:
                prompt_parts.append(f"[{doc.get('source', 'data')}]: {doc.get('content', '')[:500]}")

        if context.get("history"):
            prompt_parts.append("\n--- CONVERSATION HISTORY ---")
            for msg in context["history"][-3:]:
                prompt_parts.append(f"{msg.get('role', 'user')}: {msg.get('content', '')[:200]}")

        prompt_parts.append(f"\n--- ANALYTICS REQUEST ---\n{task}")
        return "\n".join(prompt_parts)
