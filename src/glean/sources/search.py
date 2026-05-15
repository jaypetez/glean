"""Web search source - delegates to a pluggable backend."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, ClassVar

from glean.search import build_backend
from glean.sources.base import Item
from glean.sources.registry import register_source

if TYPE_CHECKING:
    from glean.search.base import SearchBackend
    from glean.sources.base import FetchContext


@register_source("search")
class SearchSource:
    """Web search via any registered search backend.

    The 'engine' kwarg selects the backend (default: SEARCH_ENGINE env var or 'brave').
    All remaining kwargs are forwarded to the backend constructor; the backend's
    constructor signature IS the user-facing YAML API.

    Examples:
        sources:
          - type: search
            query: "AI news"
            engine: searxng
            base_url: http://searxng:8080
            categories: "news"

          - type: search
            query: "python packaging"
            engine: brave
            # reads BRAVE_API_KEY from env

          - type: search
            query: "vector databases 2025"
            engine: serper
    """

    type: ClassVar[str] = "search"

    def __init__(
        self,
        query: str,
        *,
        engine: str | None = None,
        limit: int = 10,
        **backend_kwargs: Any,
    ) -> None:
        self.query = query
        self.limit = limit
        engine_name = (engine or os.environ.get("SEARCH_ENGINE") or "brave").lower()
        self.engine = engine_name
        legacy_searxng_url = backend_kwargs.pop("searxng_url", None)
        if (
            engine_name == "searxng"
            and legacy_searxng_url is not None
            and "base_url" not in backend_kwargs
        ):
            backend_kwargs["base_url"] = legacy_searxng_url
        # Build eagerly so config validation catches unknown engines and kwargs.
        self._backend: SearchBackend = build_backend({"engine": engine_name, **backend_kwargs})

    async def fetch(self, ctx: FetchContext) -> list[Item]:
        results = await self._backend.search(self.query, http=ctx.http, limit=self.limit)
        return [
            Item(
                canonical_url=r.url,
                title=r.title,
                body=r.snippet,
                source_type="search",
                source_name=f"{self._backend.name}:{self.query}",
                published_at=r.published_at,
                score=r.score,
                raw=r.raw,
            )
            for r in results
        ]
