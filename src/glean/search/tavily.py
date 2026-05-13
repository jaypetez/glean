"""Tavily search API backend."""
from __future__ import annotations

import os
from typing import TYPE_CHECKING, ClassVar

from glean.search.base import SearchResult
from glean.search.registry import register_backend

if TYPE_CHECKING:
    import httpx


@register_backend("tavily")
class TavilyBackend:
    name: ClassVar[str] = "tavily"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        search_depth: str = "basic",
    ) -> None:
        self._api_key = api_key or os.environ.get("TAVILY_API_KEY")
        self.search_depth = search_depth

    async def search(
        self,
        query: str,
        *,
        http: httpx.AsyncClient,
        limit: int = 10,
    ) -> list[SearchResult]:
        if not self._api_key:
            raise RuntimeError("TAVILY_API_KEY is not set")
        resp = await http.post(
            "https://api.tavily.com/search",
            json={
                "api_key": self._api_key,
                "query": query,
                "max_results": limit,
                "search_depth": self.search_depth,
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        results = resp.json().get("results") or []
        out: list[SearchResult] = []
        for r in results:
            url = r.get("url", "")
            if not url:
                continue
            out.append(
                SearchResult(
                    url=url,
                    title=r.get("title", ""),
                    snippet=r.get("content", "") or "",
                    score=r.get("score"),
                    raw=r,
                )
            )
        return out
