from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar, Protocol, runtime_checkable

if TYPE_CHECKING:
    import httpx

    from glean.state.store import StateStore


@dataclass(frozen=True, slots=True)
class Item:
    """One piece of content surfaced by a Source."""

    canonical_url: str
    title: str
    body: str = ""
    summary: str | None = None
    source_type: str = ""
    source_name: str = ""
    published_at: datetime | None = None
    score: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    llm_summary: str | None = None
    relevance: float | None = None


@dataclass(slots=True)
class FetchContext:
    feed_name: str
    http: httpx.AsyncClient
    state: StateStore
    since: datetime | None = None


@runtime_checkable
class Source(Protocol):
    type: ClassVar[str]

    async def fetch(self, ctx: FetchContext) -> list[Item]: ...
