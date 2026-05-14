"""Serper.dev (Google SERP via managed scraping) backend."""
from __future__ import annotations

import os
from typing import TYPE_CHECKING, ClassVar

from glean.search.base import SearchResult
from glean.search.registry import register_backend
from glean.security.ssrf_transport import outbound_timeout

if TYPE_CHECKING:
    import httpx


@register_backend("serper")
class SerperBackend:
    name: ClassVar[str] = "serper"

    def __init__(self, *, api_key: str | None = None, country: str = "us") -> None:
        self._api_key = api_key or os.environ.get("SERPER_API_KEY")
        self.country = country

    async def search(
        self,
        query: str,
        *,
        http: httpx.AsyncClient,
        limit: int = 10,
    ) -> list[SearchResult]:
        if not self._api_key:
            raise RuntimeError("SERPER_API_KEY is not set")
        resp = await http.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": self._api_key, "Content-Type": "application/json"},
            json={"q": query, "num": limit, "gl": self.country},
            timeout=outbound_timeout(),
        )
        resp.raise_for_status()
        results = resp.json().get("organic") or []
        return [
            SearchResult(
                url=r.get("link", ""),
                title=r.get("title", ""),
                snippet=r.get("snippet", "") or "",
                raw=r,
            )
            for r in results
            if r.get("link")
        ]
