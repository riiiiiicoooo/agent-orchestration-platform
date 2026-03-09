"""
Tool Registry — MCP-compatible shared tool registry for all agents.

Provides a unified interface for agents to discover and invoke tools.
Tools are registered with schemas for validation and documentation.
"""

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


class Tool:
    """A callable tool with schema and metadata."""

    def __init__(
        self,
        name: str,
        description: str,
        handler: Callable,
        parameters: dict[str, Any],
        required_permissions: list[str] | None = None,
    ):
        self.name = name
        self.description = description
        self.handler = handler
        self.parameters = parameters
        self.required_permissions = required_permissions or []

    async def execute(self, **kwargs) -> Any:
        """Execute the tool with validated arguments."""
        return await self.handler(**kwargs)

    def to_llm_schema(self) -> dict[str, Any]:
        """Convert to LLM-compatible tool schema (OpenAI/Anthropic format)."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """
    Central registry for all agent tools.

    Supports MCP-compatible tool discovery and invocation.
    Each agent gets access to a subset of tools based on its configuration.
    """

    def __init__(self):
        self._tools: dict[str, Tool] = {}
        self._register_default_tools()

    def _register_default_tools(self) -> None:
        """Register the default tool set for Apex Financial Services."""

        # Database query tool
        self.register(Tool(
            name="database_query",
            description="Execute a read-only SQL query against the claims/policy database",
            handler=self._database_query_handler,
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "SQL query (SELECT only)"},
                    "database": {"type": "string", "enum": ["claims", "policies", "analytics"]},
                },
                "required": ["query", "database"],
            },
        ))

        # Document search (vector + BM25 hybrid)
        self.register(Tool(
            name="document_search",
            description="Search documents using hybrid vector + keyword search",
            handler=self._document_search_handler,
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "doc_type": {"type": "string", "enum": ["policy", "claim", "medical", "invoice"]},
                    "top_k": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
        ))

        # FAQ search
        self.register(Tool(
            name="faq_search",
            description="Search the FAQ knowledge base for customer-facing answers",
            handler=self._faq_search_handler,
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Customer question"},
                    "category": {"type": "string", "enum": ["claims", "billing", "policy", "general"]},
                },
                "required": ["query"],
            },
        ))

        # Claims API
        self.register(Tool(
            name="claims_api",
            description="Interact with the claims management system API",
            handler=self._claims_api_handler,
            parameters={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["get_status", "create", "update", "search"]},
                    "claim_id": {"type": "string"},
                    "data": {"type": "object"},
                },
                "required": ["action"],
            },
        ))

        # Status lookup
        self.register(Tool(
            name="status_lookup",
            description="Look up the status of a claim, policy, or payment",
            handler=self._status_lookup_handler,
            parameters={
                "type": "object",
                "properties": {
                    "entity_type": {"type": "string", "enum": ["claim", "policy", "payment"]},
                    "reference_id": {"type": "string"},
                },
                "required": ["entity_type", "reference_id"],
            },
        ))

        # Risk model
        self.register(Tool(
            name="risk_model",
            description="Run risk scoring model against a set of underwriting factors",
            handler=self._risk_model_handler,
            parameters={
                "type": "object",
                "properties": {
                    "risk_factors": {"type": "object"},
                    "carrier": {"type": "string"},
                    "line_of_business": {"type": "string"},
                },
                "required": ["risk_factors", "carrier"],
            },
        ))

        # Policy lookup
        self.register(Tool(
            name="policy_lookup",
            description="Retrieve policy details by policy number or named insured",
            handler=self._policy_lookup_handler,
            parameters={
                "type": "object",
                "properties": {
                    "policy_number": {"type": "string"},
                    "named_insured": {"type": "string"},
                    "effective_date": {"type": "string"},
                },
            },
        ))

        # Ticket creation
        self.register(Tool(
            name="ticket_create",
            description="Create a support ticket for follow-up",
            handler=self._ticket_create_handler,
            parameters={
                "type": "object",
                "properties": {
                    "subject": {"type": "string"},
                    "description": {"type": "string"},
                    "priority": {"type": "string", "enum": ["low", "medium", "high", "urgent"]},
                    "assignee_group": {"type": "string"},
                },
                "required": ["subject", "description", "priority"],
            },
        ))

        # OCR extraction
        self.register(Tool(
            name="ocr_extract",
            description="Extract text and structured data from a document image or PDF",
            handler=self._ocr_extract_handler,
            parameters={
                "type": "object",
                "properties": {
                    "document_id": {"type": "string"},
                    "extraction_type": {"type": "string", "enum": ["full_text", "structured", "table"]},
                },
                "required": ["document_id"],
            },
        ))

        # Document classify
        self.register(Tool(
            name="document_classify",
            description="Classify a document by type and extract metadata",
            handler=self._document_classify_handler,
            parameters={
                "type": "object",
                "properties": {
                    "document_id": {"type": "string"},
                    "content_preview": {"type": "string"},
                },
                "required": ["document_id"],
            },
        ))

        # Data normalize
        self.register(Tool(
            name="data_normalize",
            description="Normalize extracted data into standard schema",
            handler=self._data_normalize_handler,
            parameters={
                "type": "object",
                "properties": {
                    "raw_data": {"type": "object"},
                    "target_schema": {"type": "string"},
                },
                "required": ["raw_data", "target_schema"],
            },
        ))

        # Report generate
        self.register(Tool(
            name="report_generate",
            description="Generate a formatted report from analytics data",
            handler=self._report_generate_handler,
            parameters={
                "type": "object",
                "properties": {
                    "report_type": {"type": "string", "enum": ["loss_ratio", "claims_summary", "carrier_performance", "custom"]},
                    "date_range": {"type": "object", "properties": {"start": {"type": "string"}, "end": {"type": "string"}}},
                    "filters": {"type": "object"},
                },
                "required": ["report_type"],
            },
        ))

        # Trend analysis
        self.register(Tool(
            name="trend_analyze",
            description="Analyze trends in claims, premiums, or operational metrics",
            handler=self._trend_analyze_handler,
            parameters={
                "type": "object",
                "properties": {
                    "metric": {"type": "string"},
                    "dimension": {"type": "string", "enum": ["time", "carrier", "line_of_business", "region"]},
                    "period": {"type": "string", "enum": ["monthly", "quarterly", "yearly"]},
                },
                "required": ["metric", "dimension"],
            },
        ))

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def get_tools(self, tool_names: list[str]) -> list[Tool]:
        return [self._tools[name] for name in tool_names if name in self._tools]

    def __len__(self) -> int:
        return len(self._tools)

    # --- Tool handler stubs (connected to real services in production) ---

    async def _database_query_handler(self, query: str, database: str) -> dict:
        """Execute read-only SQL query."""
        # In production: connects to Supabase PostgreSQL via asyncpg
        return {"status": "success", "rows": [], "query": query, "database": database}

    async def _document_search_handler(self, query: str, doc_type: str = None, top_k: int = 5) -> dict:
        return {"status": "success", "results": [], "query": query}

    async def _faq_search_handler(self, query: str, category: str = None) -> dict:
        return {"status": "success", "answers": [], "query": query}

    async def _claims_api_handler(self, action: str, claim_id: str = None, data: dict = None) -> dict:
        return {"status": "success", "action": action}

    async def _status_lookup_handler(self, entity_type: str, reference_id: str) -> dict:
        return {"status": "success", "entity_type": entity_type, "reference_id": reference_id}

    async def _risk_model_handler(self, risk_factors: dict, carrier: str, line_of_business: str = None) -> dict:
        return {"status": "success", "risk_score": 0, "carrier": carrier}

    async def _policy_lookup_handler(self, policy_number: str = None, named_insured: str = None, effective_date: str = None) -> dict:
        return {"status": "success", "policy": None}

    async def _ticket_create_handler(self, subject: str, description: str, priority: str, assignee_group: str = None) -> dict:
        return {"status": "success", "ticket_id": "TKT-0000"}

    async def _ocr_extract_handler(self, document_id: str, extraction_type: str = "full_text") -> dict:
        return {"status": "success", "document_id": document_id}

    async def _document_classify_handler(self, document_id: str, content_preview: str = None) -> dict:
        return {"status": "success", "document_id": document_id, "classification": None}

    async def _data_normalize_handler(self, raw_data: dict, target_schema: str) -> dict:
        return {"status": "success", "normalized": raw_data}

    async def _report_generate_handler(self, report_type: str, date_range: dict = None, filters: dict = None) -> dict:
        return {"status": "success", "report_type": report_type}

    async def _trend_analyze_handler(self, metric: str, dimension: str, period: str = "monthly") -> dict:
        return {"status": "success", "metric": metric, "dimension": dimension}
