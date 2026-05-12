from __future__ import annotations

import os
from typing import ClassVar

from glean.sources.base import FetchContext, Item
from glean.sources.registry import register_source


@register_source("search")
class SearchSource:
    """Live web search via Brave, Tavily, or self-hosted SearXNG.

    Backend is chosen by the `engine` arg (defaults to env var SEARCH_ENGINE
    or 'brave'). Each backend reads its own API key from env.
    """

    type: ClassVar[str] = "search"

    def __init__(
        self,
        query: str,
        *,
        engine: str | None = None,
        limit: int = 10,
        searxng_url: str | None = None,
    ) -> None:
        self.query = query
        self.engine = (engine or os.environ.get("SEARCH_ENGINE") or "brave").lower()
        self.limit = limit
        self.searxng_url = searxng_url or os.environ.get("SEARXNG_URL")

    async def fetch(self, ctx: FetchContext) -> list[Item]:
        if self.engine == "brave":
            return await self._brave(ctx)
        if self.engine == "tavily":
            return await self._tavily(ctx)
        if self.engine == "searxng":
            return await self._searxng(ctx)
        raise ValueError(f"unknown search engine: {self.engine!r}")

    async def _brave(self, ctx: FetchContext) -> list[Item]:
        key = os.environ.get("BRAVE_API_KEY")
        if not key:
            raise RuntimeError("BRAVE_API_KEY is not set")
        resp = await ctx.http.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": self.query, "count": self.limit},
            headers={"X-Subscription-Token": key, "Accept": "application/json"},
            timeout=30.0,
        )
        resp.raise_for_status()
        results = resp.json().get("web", {}).get("results", []) or []
        return [
            Item(
                canonical_url=r.get("url", ""),
                title=r.get("title", ""),
                body=r.get("description", "") or "",
                source_type="search",
                source_name=f"brave:{self.query}",
                raw=r,
            )
            for r in results
            if r.get("url")
        ]

    async def _tavily(self, ctx: FetchContext) -> list[Item]:
        key = os.environ.get("TAVILY_API_KEY")
        if not key:
            raise RuntimeError("TAVILY_API_KEY is not set")
        resp = await ctx.http.post(
            "https://api.tavily.com/search",
            json={
                "api_key": key,
                "query": self.query,
                "max_results": self.limit,
                "search_depth": "basic",
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        results = resp.json().get("results", []) or []
        return [
            Item(
                canonical_url=r.get("url", ""),
                title=r.get("title", ""),
                body=r.get("content", "") or "",
                source_type="search",
                source_name=f"tavily:{self.query}",
                raw=r,
            )
            for r in results
            if r.get("url")
        ]

    async def _searxng(self, ctx: FetchContext) -> list[Item]:
        if not self.searxng_url:
            raise RuntimeError("SEARXNG_URL is not set")
        resp = await ctx.http.get(
            self.searxng_url.rstrip("/") + "/search",
            params={"q": self.query, "format": "json"},
            timeout=30.0,
        )
        resp.raise_for_status()
        results = (resp.json().get("results") or [])[: self.limit]
        return [
            Item(
                canonical_url=r.get("url", ""),
                title=r.get("title", ""),
                body=r.get("content", "") or "",
                source_type="search",
                source_name=f"searxng:{self.query}",
                raw=r,
            )
            for r in results
            if r.get("url")
        ]
