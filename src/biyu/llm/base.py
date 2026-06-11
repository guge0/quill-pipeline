from __future__ import annotations

import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator


@dataclass
class LLMResponse:
    text: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost: float = 0.0
    finish_reason: str | None = None
    raw: dict | None = None
    reasoning_content: str | None = None  # R1等推理模型的思维链


@dataclass
class EmbeddingResponse:
    embedding: list[float]
    model: str
    prompt_tokens: int = 0
    raw: dict | None = None


def resolve_env_vars(value: str) -> str:
    """Replace ${ENV_VAR} patterns with environment variable values."""
    def _replacer(m: re.Match) -> str:
        return os.environ.get(m.group(1), m.group(0))
    return re.sub(r"\$\{(\w+)\}", _replacer, value)


class LLMAdapter(ABC):
    """Abstract base class for LLM providers."""

    def __init__(
        self,
        model_name: str,
        api_key: str,
        base_url: str | None = None,
        max_tokens: int = 8000,
        cost_per_1k_input: float = 0.0,
        cost_per_1k_output: float = 0.0,
        **kwargs,
    ):
        self.model_name = model_name
        self.api_key = resolve_env_vars(api_key)
        self.base_url = base_url
        self.max_tokens = max_tokens
        self.cost_per_1k_input = cost_per_1k_input
        self.cost_per_1k_output = cost_per_1k_output

    def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        return (prompt_tokens * self.cost_per_1k_input + completion_tokens * self.cost_per_1k_output) / 1000.0

    @abstractmethod
    async def generate(self, messages: list[dict], **kwargs) -> LLMResponse:
        ...

    @abstractmethod
    async def stream(self, messages: list[dict], **kwargs) -> AsyncIterator[str]:
        ...

    async def embed(self, text: str, **kwargs) -> EmbeddingResponse:
        raise NotImplementedError(f"{self.__class__.__name__} does not support embeddings")

    def _build_response(self, data: dict, text: str) -> LLMResponse:
        usage = data.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)
        cost = self.estimate_cost(prompt_tokens, completion_tokens)
        choices = data.get("choices", [{}])
        finish_reason = choices[0].get("finish_reason") if choices else None
        return LLMResponse(
            text=text,
            model=data.get("model", self.model_name),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost=cost,
            finish_reason=finish_reason,
            raw=data,
        )
