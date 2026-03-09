"""
OpenAI Provider — GPT-4o integration for structured reasoning tasks.

Supports GPT-4o (primary reasoning), GPT-4 Turbo (fallback),
and GPT-3.5 Turbo (cost-optimized simple tasks).
"""

import time
import logging
from typing import Any

import openai

from src.providers.base import BaseLLMProvider, LLMResponse
from src.config.settings import settings

logger = logging.getLogger(__name__)

OPENAI_PRICING = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
}


class OpenAIProvider(BaseLLMProvider):
    """OpenAI GPT provider with structured output support."""

    def __init__(self):
        self.client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

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

        request_kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
        }

        if tools:
            request_kwargs["tools"] = [
                tool.to_llm_schema() if hasattr(tool, "to_llm_schema") else tool
                for tool in tools
            ]

        try:
            response = await self.client.chat.completions.create(**request_kwargs)

            choice = response.choices[0]
            content = choice.message.content or ""

            tool_calls = []
            if choice.message.tool_calls:
                import json
                for tc in choice.message.tool_calls:
                    tool_calls.append({
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": json.loads(tc.function.arguments),
                    })

            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens
            cost = self.estimate_cost(model, input_tokens, output_tokens)

            return LLMResponse(
                content=content,
                total_tokens=input_tokens + output_tokens,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost=cost,
                model=model,
                provider="openai",
                tool_calls=tool_calls,
                finish_reason=choice.finish_reason or "",
                latency_ms=(time.monotonic() - start_time) * 1000,
            )

        except openai.RateLimitError:
            logger.warning("OpenAI rate limit hit for model %s", model)
            raise
        except Exception as e:
            logger.error("OpenAI API error: %s", e)
            raise

    def estimate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        pricing = OPENAI_PRICING.get(model, {"input": 2.5, "output": 10.0})
        return (
            (input_tokens / 1_000_000) * pricing["input"]
            + (output_tokens / 1_000_000) * pricing["output"]
        )

    def count_tokens(self, text: str, model: str) -> int:
        return len(text) // 4
