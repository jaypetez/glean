"""Brave Search API backend."""
from __future__ import annotations

import os
from typing import TYPE_CHECKING, ClassVar

from glean.search.base import SearchResult
from glean.search.registry import register_backend
from glean.security.ssrf_transport import outbound_timeout

if TYPE_CHECKING:
    import httpx


@register_backend("brave")
class BraveBackend:
    name: ClassVar[str] = "brave"

    def __init__(self, *, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("BRAVE_API_KEY")

    async def search(
        self,
        query: str,
        *,
        http: httpx.AsyncClient,
        limit: int = 10,
    ) -> list[SearchResult]:
        if not self._api_key:
            raise RuntimeError("BRAVE_API_KEY is not set")
        resp = await http.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": limit},
            headers={"X-Subscription-Token": self._api_key, "Accept": "application/json"},
            timeout=outbound_timeout(),
        )
        resp.raise_for_status()
        results = resp.json().get("web", {}).get("results", []) or []
        return [
            SearchResult(
                url=r.get("url", ""),
                title=r.get("title", ""),
                snippet=r.get("description", "") or "",
                raw=r,
            )
            for r in results
            if r.get("url")
        ]
