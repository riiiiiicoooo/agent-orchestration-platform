"""
Model Router — Multi-provider LLM routing with failover and cost optimization.

Routes requests to the appropriate LLM provider based on task type,
handles failover between providers, and tracks cost per request.
"""

import logging
from typing import Any

from src.providers.base import BaseLLMProvider, LLMResponse
from src.providers.anthropic import AnthropicProvider
from src.providers.openai import OpenAIProvider

logger = logging.getLogger(__name__)

# Model-to-provider mapping
MODEL_PROVIDER_MAP = {
    "claude-3.5-sonnet": "anthropic",
    "claude-3-haiku": "anthropic",
    "claude-3-opus": "anthropic",
    "claude-sonnet-4": "anthropic",
    "gpt-4o": "openai",
    "gpt-4-turbo": "openai",
    "gpt-3.5-turbo": "openai",
    "gpt-4o-mini": "openai",
}

# Failover mapping — if primary fails, try secondary
FAILOVER_MAP = {
    "claude-3.5-sonnet": "gpt-4o",
    "gpt-4o": "claude-3.5-sonnet",
    "claude-3-haiku": "gpt-4o-mini",
    "gpt-4o-mini": "claude-3-haiku",
}


class ModelRouter:
    """
    Multi-provider model router with intelligent failover.

    Responsibilities:
    - Route model requests to correct provider
    - Handle provider failover on errors
    - Track per-model cost attribution
    - Classify intents using fast routing model
    """

    def __init__(
        self,
        primary_provider: str = "anthropic",
        fallback_provider: str = "openai",
        routing_provider: str = "anthropic",
    ):
        self.primary_provider = primary_provider
        self.fallback_provider = fallback_provider
        self.routing_provider = routing_provider

        # Initialize providers
        self.providers: dict[str, BaseLLMProvider] = {
            "anthropic": AnthropicProvider(),
            "openai": OpenAIProvider(),
        }

        # Cost tracking
        self.total_cost = 0.0
        self.cost_by_model: dict[str, float] = {}
        self.cost_by_provider: dict[str, float] = {}

    async def generate(
        self,
        model: str,
        prompt: str,
        tools: list | None = None,
        tool_results: list | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        **kwargs,
    ) -> LLMResponse:
        """
        Generate a completion, routing to the correct provider.
        Falls back to secondary provider on failure.
        """
        provider_name = MODEL_PROVIDER_MAP.get(model, self.primary_provider)
        provider = self.providers[provider_name]

        messages = [{"role": "user", "content": prompt}]

        try:
            response = await provider.generate(
                model=model,
                messages=messages,
                tools=tools,
                tool_results=tool_results,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs,
            )

            # Track costs
            self._track_cost(model, provider_name, response.cost)
            return response

        except Exception as e:
            logger.warning(
                "Provider %s failed for model %s: %s — attempting failover",
                provider_name, model, e,
            )

            # Try failover
            failover_model = FAILOVER_MAP.get(model)
            if failover_model:
                failover_provider_name = MODEL_PROVIDER_MAP.get(failover_model)
                failover_provider = self.providers.get(failover_provider_name)
                if failover_provider:
                    response = await failover_provider.generate(
                        model=failover_model,
                        messages=messages,
                        tools=tools,
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )
                    self._track_cost(failover_model, failover_provider_name, response.cost)
                    return response

            raise

    async def classify(
        self,
        prompt: str,
        user_input: str,
        session_context: dict[str, Any] | None = None,
    ) -> str:
        """
        Fast intent classification using routing model (Haiku).
        Optimized for speed (<200ms) and low cost.
        """
        messages = [
            {"role": "user", "content": f"{prompt}\n\nUser request: {user_input}"},
        ]

        response = await self.providers[self.routing_provider].generate(
            model="claude-3-haiku",
            messages=messages,
            max_tokens=256,
            temperature=0.0,
        )

        self._track_cost("claude-3-haiku", self.routing_provider, response.cost)
        return response.content

    def _track_cost(self, model: str, provider: str, cost: float) -> None:
        self.total_cost += cost
        self.cost_by_model[model] = self.cost_by_model.get(model, 0.0) + cost
        self.cost_by_provider[provider] = self.cost_by_provider.get(provider, 0.0) + cost

    def get_cost_summary(self) -> dict[str, Any]:
        return {
            "total_cost": self.total_cost,
            "by_model": dict(self.cost_by_model),
            "by_provider": dict(self.cost_by_provider),
        }
