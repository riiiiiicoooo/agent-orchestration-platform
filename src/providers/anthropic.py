"""
Anthropic Provider — Claude integration with prompt caching support.

Supports Claude 3.5 Sonnet (primary extraction), Claude 3 Haiku (fast routing),
and Claude 3 Opus (complex reasoning fallback).
"""

import time
import logging
from typing import Any

import anthropic

from src.providers.base import BaseLLMProvider, LLMResponse
from src.config.settings import settings

logger = logging.getLogger(__name__)

# Pricing per 1M tokens (as of March 2026)
ANTHROPIC_PRICING = {
    "claude-3.5-sonnet": {"input": 3.00, "output": 15.00},
    "claude-3-haiku": {"input": 0.25, "output": 1.25},
    "claude-3-opus": {"input": 15.00, "output": 75.00},
    "claude-sonnet-4": {"input": 3.00, "output": 15.00},
}


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude provider with prompt caching and MCP support."""

    def __init__(self):
        self.client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

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
        start_time = time.monotonic()

        # Build request
        request_kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
        }

        # Add system prompt with cache control for prompt caching
        if kwargs.get("system"):
            request_kwargs["system"] = [
                {
                    "type": "text",
                    "text": kwargs["system"],
                    "cache_control": {"type": "ephemeral"},
                }
            ]

        # Add tools if provided
        if tools:
            request_kwargs["tools"] = [
                tool.to_llm_schema() if hasattr(tool, "to_llm_schema") else tool
                for tool in tools
            ]

        try:
            response = await self.client.messages.create(**request_kwargs)

            # Extract content
            content = ""
            tool_calls = []
            for block in response.content:
                if block.type == "text":
                    content += block.text
                elif block.type == "tool_use":
                    tool_calls.append({
                        "id": block.id,
                        "name": block.name,
                        "arguments": block.input,
                    })

            # Calculate cost
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            cost = self.estimate_cost(model, input_tokens, output_tokens)

            # Check for cache hits (prompt caching savings)
            cache_read_tokens = getattr(response.usage, "cache_read_input_tokens", 0)
            if cache_read_tokens:
                cache_savings = (cache_read_tokens / 1_000_000) * ANTHROPIC_PRICING.get(model, {}).get("input", 3.0) * 0.9
                logger.debug("Prompt cache hit: %d tokens, saved $%.4f", cache_read_tokens, cache_savings)

            return LLMResponse(
                content=content,
                total_tokens=input_tokens + output_tokens,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost=cost,
                model=model,
                provider="anthropic",
                tool_calls=tool_calls,
                finish_reason=response.stop_reason or "",
                latency_ms=(time.monotonic() - start_time) * 1000,
            )

        except anthropic.RateLimitError:
            logger.warning("Anthropic rate limit hit for model %s", model)
            raise
        except Exception as e:
            logger.error("Anthropic API error: %s", e)
            raise

    def estimate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        pricing = ANTHROPIC_PRICING.get(model, {"input": 3.0, "output": 15.0})
        return (
            (input_tokens / 1_000_000) * pricing["input"]
            + (output_tokens / 1_000_000) * pricing["output"]
        )

    def count_tokens(self, text: str, model: str) -> int:
        # Approximate: ~4 chars per token for Claude
        return len(text) // 4
