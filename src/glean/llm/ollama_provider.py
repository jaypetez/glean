from __future__ import annotations

import json
from typing import Any, ClassVar

import ollama

from glean.llm.common import (
    INJECTION_GUARD_SYSTEM_PROMPT,
    item_as_prompt_context,
    items_as_prompt_context,
    parse_score,
)
from glean.llm.registry import register_provider
from glean.logging import get_logger
from glean.security.ssrf import is_external_http_url, validate_provider_base_url
from glean.security.ssrf_transport import SSRFGuardedTransport, outbound_timeout
from glean.sources.base import Item

logger = get_logger(__name__)


@register_provider("ollama")
class OllamaProvider:
    name: ClassVar[str] = "ollama"

    def __init__(
        self,
        model: str = "qwen2.5:7b",
        base_url: str | None = None,
        timeout_s: float = 60.0,
        api_key: str | None = None,
    ) -> None:
        del api_key  # unused
        self.model = model
        self.base_url = validate_provider_base_url("ollama", base_url or "http://ollama:11434")
        self.timeout_s = timeout_s
        if is_external_http_url(self.base_url):
            logger.warning("ollama_external_http_base_url", base_url=self.base_url)
        self._client = ollama.AsyncClient(
            host=self.base_url,
            timeout=outbound_timeout(read=timeout_s),
            follow_redirects=False,
            transport=SSRFGuardedTransport(allow_private=True),
        )

    async def rank(self, item: Item, prompt: str) -> float:
        system = (
            f"{INJECTION_GUARD_SYSTEM_PROMPT}\n\n"
            f"{prompt.strip()}\n\n"
            "Respond with ONLY a single number between 0 and 1. No prose."
        )
        user = item_as_prompt_context(item)
        resp = await self._client.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            options={"temperature": 0.0, "num_predict": 16},
        )
        return parse_score(resp["message"]["content"])

    async def summarize(self, item: Item, prompt: str) -> str:
        system = (
            f"{INJECTION_GUARD_SYSTEM_PROMPT}\n\n"
            f"{prompt.strip() or 'Summarize the following content in one sentence.'}"
        )
        user = item_as_prompt_context(item)
        resp = await self._client.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            options={"temperature": 0.3, "num_predict": 256},
        )
        return (resp["message"]["content"] or "").strip()

    async def digest(self, items: list[Item], prompt: str) -> str:
        system = (
            f"{INJECTION_GUARD_SYSTEM_PROMPT}\n\n"
            f"{prompt.strip() or 'Write a 1-line digest header for the items below.'}"
        )
        user = items_as_prompt_context(items)
        resp = await self._client.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            options={"temperature": 0.3, "num_predict": 512},
        )
        return (resp["message"]["content"] or "").strip()

    async def extract(
        self,
        item: Item,
        prompt: str,
        output_schema: dict[str, Any],
        *,
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        system = (system_prompt or "").strip() or "Extract structured data as JSON."
        user = f"{prompt}\n\n{item_as_prompt_context(item)}"
        resp = await self._client.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            format=output_schema,
            options={"temperature": 0.0},
        )
        raw = (resp["message"]["content"] or "{}").strip()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    async def aclose(self) -> None:
        # ollama AsyncClient uses httpx internally; close its client
        client = getattr(self._client, "_client", None)
        if client is not None:
            aclose = getattr(client, "aclose", None)
            if aclose:
                await aclose()
