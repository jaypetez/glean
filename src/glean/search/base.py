"""Search backend protocol and normalized result type."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar, Protocol, runtime_checkable

if TYPE_CHECKING:
    import httpx


@dataclass(frozen=True, slots=True)
class SearchResult:
    """Normalized search result — common fields across all backends."""

    url: str
    title: str
    snippet: str
    score: float | None = None
    published_at: datetime | None = None
    engine: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class SearchBackend(Protocol):
    """Protocol every search backend must satisfy."""

    name: ClassVar[str]

    async def search(
        self,
        query: str,
        *,
        http: httpx.AsyncClient,
        limit: int = 10,
    ) -> list[SearchResult]: ...
