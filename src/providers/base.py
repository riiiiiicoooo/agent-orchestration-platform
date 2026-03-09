"""
LLM Provider Base — Abstract interface for multi-provider LLM support.

Enables swapping between OpenAI, Anthropic, Azure, and other providers
without changing agent code. Tracks cost per call for budget enforcement.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLMResponse:
    """Standardized response from any LLM provider."""
    content: str = ""
    total_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    model: str = ""
    provider: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    finish_reason: str = ""
    latency_ms: float = 0.0


class BaseLLMProvider(ABC):
    """Abstract LLM provider interface."""

    @abstractmethod
    async def generate(
        self,
        model: str,
        messages: list[dict[str, str]],
        tools: list[dict] | None = None,
        tool_results: list[dict] | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        **kwargs,
    ) -> LLMResponse:
        """Generate a completion from the LLM."""
        ...

    @abstractmethod
    def estimate_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """Estimate cost for a given token count."""
        ...

    @abstractmethod
    def count_tokens(self, text: str, model: str) -> int:
        """Count tokens for a given text."""
        ...
