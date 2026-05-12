from __future__ import annotations

import os
from typing import ClassVar

import anthropic
from anthropic.types import TextBlock

from glean.llm.common import (
    item_as_prompt_context,
    items_as_prompt_context,
    parse_score,
)
from glean.llm.registry import register_provider
from glean.sources.base import Item


@register_provider("anthropic")
class AnthropicProvider:
    name: ClassVar[str] = "anthropic"

    def __init__(
        self,
        model: str = "claude-haiku-4-5",
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_s: float = 60.0,
    ) -> None:
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        self.model = model
        self._client = anthropic.AsyncAnthropic(
            api_key=key, base_url=base_url, timeout=timeout_s
        )

    async def _complete(self, system: str, user: str, *, max_tokens: int) -> str:
        resp = await self._client.messages.create(
            model=self.model,
            system=system,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": user}],
        )
        text_parts = [b.text for b in resp.content if isinstance(b, TextBlock)]
        return "".join(text_parts).strip()

    async def rank(self, item: Item, prompt: str) -> float:
        system = (
            f"{prompt.strip()}\n\n"
            "Respond with ONLY a single number between 0 and 1. No prose."
        )
        out = await self._complete(system, item_as_prompt_context(item), max_tokens=16)
        return parse_score(out)

    async def summarize(self, item: Item, prompt: str) -> str:
        return await self._complete(
            prompt.strip() or "Summarize the following content in one sentence.",
            item_as_prompt_context(item),
            max_tokens=256,
        )

    async def digest(self, items: list[Item], prompt: str) -> str:
        return await self._complete(
            prompt.strip() or "Write a 1-line digest header for the items below.",
            items_as_prompt_context(items),
            max_tokens=256,
        )

    async def aclose(self) -> None:
        await self._client.close()
