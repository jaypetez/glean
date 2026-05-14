"""MWMBL community-crawled search engine (free, no API key)."""
from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from glean.search.base import SearchResult
from glean.search.registry import register_backend
from glean.security.ssrf import validate_url
from glean.security.ssrf_transport import outbound_timeout

if TYPE_CHECKING:
    import httpx


@register_backend("mwmbl")
class MWMBLBackend:
    name: ClassVar[str] = "mwmbl"

    def __init__(self, *, base_url: str = "https://api.mwmbl.org") -> None:
        self.base_url = validate_url(base_url).rstrip("/")

    async def search(
        self,
        query: str,
        *,
        http: httpx.AsyncClient,
        limit: int = 10,
    ) -> list[SearchResult]:
        resp = await http.get(
            f"{self.base_url}/search/api/v1/search/",
            params={"s": query},
            timeout=outbound_timeout(),
        )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            results = data.get("results") or []
        else:
            results = data
        out: list[SearchResult] = []
        for r in results[:limit]:
            url = r.get("url") or ""
            if not url:
                continue
            out.append(
                SearchResult(
                    url=url,
                    title=r.get("title") or "",
                    snippet=r.get("extract") or "",
                    raw=r,
                )
            )
        return out
