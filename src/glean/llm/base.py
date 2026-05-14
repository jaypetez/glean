from __future__ import annotations

from typing import Any, ClassVar, Protocol, runtime_checkable

from glean.sources.base import Item


@runtime_checkable
class LLMProvider(Protocol):
    name: ClassVar[str]
    model: str

    async def rank(self, item: Item, prompt: str) -> float:
        """Return relevance in [0, 1]."""

    async def summarize(self, item: Item, prompt: str) -> str:
        """Return a plain-text summary; renderer adds markup."""

    async def digest(self, items: list[Item], prompt: str) -> str:
        """Optional: synthesize a header/intro line for the digest."""

    async def extract(
        self,
        item: Item,
        prompt: str,
        output_schema: dict[str, Any],
        *,
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        """Extract structured data matching output_schema (JSON Schema dict).

        Returns {} on parse/extraction failure.
        """

    async def aclose(self) -> None:
        pass
