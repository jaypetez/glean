from __future__ import annotations

import json
import os
from typing import Any, ClassVar

import openai

from glean.llm.common import (
    item_as_prompt_context,
    items_as_prompt_context,
    parse_score,
)
from glean.llm.registry import register_provider
from glean.sources.base import Item


@register_provider("openai")
class OpenAIProvider:
    name: ClassVar[str] = "openai"

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_s: float = 60.0,
    ) -> None:
        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        self.model = model
        self._client = openai.AsyncOpenAI(
            api_key=key, base_url=base_url, timeout=timeout_s
        )

    async def _chat(self, system: str, user: str, *, max_tokens: int) -> str:
        resp = await self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=max_tokens,
            temperature=0.3,
        )
        return (resp.choices[0].message.content or "").strip()

    async def rank(self, item: Item, prompt: str) -> float:
        system = (
            f"{prompt.strip()}\n\n"
            "Respond with ONLY a single number between 0 and 1. No prose."
        )
        out = await self._chat(system, item_as_prompt_context(item), max_tokens=16)
        return parse_score(out)

    async def summarize(self, item: Item, prompt: str) -> str:
        return await self._chat(
            prompt.strip() or "Summarize the following content in one sentence.",
            item_as_prompt_context(item),
            max_tokens=256,
        )

    async def digest(self, items: list[Item], prompt: str) -> str:
        return await self._chat(
            prompt.strip() or "Write a 1-line digest header for the items below.",
            items_as_prompt_context(items),
            max_tokens=256,
        )

    async def extract(
        self,
        item: Item,
        prompt: str,
        output_schema: dict[str, Any],
        *,
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        resp = await self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt or "Extract structured data."},
                {"role": "user", "content": f"{prompt}\n\n{item_as_prompt_context(item)}"},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "extraction",
                    "schema": output_schema,
                    "strict": True,
                },
            },
            max_tokens=1024,
            temperature=0.0,
        )
        raw = (resp.choices[0].message.content or "{}").strip()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    async def aclose(self) -> None:
        await self._client.close()
