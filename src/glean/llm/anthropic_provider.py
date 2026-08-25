from __future__ import annotations

import os
from typing import Any, ClassVar, cast

import anthropic
import httpx2
from anthropic.types import TextBlock

from glean.llm.common import (
    INJECTION_GUARD_SYSTEM_PROMPT,
    item_as_prompt_context,
    items_as_prompt_context,
    parse_score,
)
from glean.llm.registry import register_provider
from glean.security.ssrf import is_localhost_url, validate_provider_base_url
from glean.security.ssrf_transport import SSRFGuardedHttpx2Transport, outbound_timeout_httpx2
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
        validated_base_url = (
            validate_provider_base_url("anthropic", base_url) if base_url is not None else None
        )
        allow_private = bool(validated_base_url and is_localhost_url(validated_base_url))
        timeout = outbound_timeout_httpx2(read=timeout_s)
        http_client = httpx2.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            transport=SSRFGuardedHttpx2Transport(allow_private=allow_private),
        )
        self._client = anthropic.AsyncAnthropic(
            api_key=key,
            base_url=validated_base_url,
            timeout=timeout,
            http_client=http_client,
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
            f"{INJECTION_GUARD_SYSTEM_PROMPT}\n\n"
            f"{prompt.strip()}\n\n"
            "Respond with ONLY a single number between 0 and 1. No prose."
        )
        out = await self._complete(system, item_as_prompt_context(item), max_tokens=16)
        return parse_score(out)

    async def summarize(self, item: Item, prompt: str) -> str:
        system = (
            f"{INJECTION_GUARD_SYSTEM_PROMPT}\n\n"
            f"{prompt.strip() or 'Summarize the following content in one sentence.'}"
        )
        return await self._complete(
            system,
            item_as_prompt_context(item),
            max_tokens=256,
        )

    async def digest(self, items: list[Item], prompt: str) -> str:
        system = (
            f"{INJECTION_GUARD_SYSTEM_PROMPT}\n\n"
            f"{prompt.strip() or 'Write a 1-line digest header for the items below.'}"
        )
        return await self._complete(
            system,
            items_as_prompt_context(items),
            max_tokens=512,
        )

    async def extract(
        self,
        item: Item,
        prompt: str,
        output_schema: dict[str, Any],
        *,
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        tool_def = {
            "name": "extract",
            "description": "Extract structured data from the content.",
            "input_schema": output_schema,
        }
        user = f"{prompt}\n\n{item_as_prompt_context(item)}"
        resp = await self._client.messages.create(
            model=self.model,
            system=system_prompt or "Extract structured data.",
            max_tokens=1024,
            tools=cast(Any, [tool_def]),
            tool_choice=cast(Any, {"type": "tool", "name": "extract"}),
            messages=cast(Any, [{"role": "user", "content": user}]),
        )
        for block in resp.content:
            if getattr(block, "name", None) == "extract":
                input_data = getattr(block, "input", None)
                if isinstance(input_data, dict):
                    return dict(input_data)
                return {}
        return {}

    async def aclose(self) -> None:
        await self._client.close()
