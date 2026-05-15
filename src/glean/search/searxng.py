"""SearXNG self-hosted metasearch backend."""

from __future__ import annotations

import os
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any, ClassVar

import httpx

from glean.search.base import SearchResult
from glean.search.registry import register_backend
from glean.security.ssrf import validate_url
from glean.security.ssrf_transport import SSRF_ALLOW_PRIVATE_EXTENSION, outbound_timeout


def _parse_published_at(value: str | None) -> datetime | None:
    if not value:
        return None
    timestamp = value[:-1] + "+00:00" if value.endswith("Z") else value
    with suppress(ValueError):
        parsed = datetime.fromisoformat(timestamp)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


@register_backend("searxng")
class SearXNGBackend:
    name: ClassVar[str] = "searxng"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        categories: str | None = None,
        time_range: str | None = None,
        safesearch: int | None = None,
    ) -> None:
        resolved_base_url = (base_url or os.environ.get("SEARXNG_URL") or "").rstrip("/")
        self.base_url = (
            validate_url(resolved_base_url, allow_private=True).rstrip("/")
            if resolved_base_url
            else ""
        )
        self.categories = categories
        self.time_range = time_range
        self.safesearch = safesearch

    async def search(
        self,
        query: str,
        *,
        http: httpx.AsyncClient,
        limit: int = 10,
    ) -> list[SearchResult]:
        if not self.base_url:
            raise RuntimeError(
                "SearXNG base_url is not configured. "
                "Set 'base_url' in the source spec or SEARXNG_URL env var."
            )
        params: dict[str, Any] = {"q": query, "format": "json"}
        if self.categories is not None:
            params["categories"] = self.categories
        if self.safesearch is not None:
            params["safesearch"] = self.safesearch
        if self.time_range:
            params["time_range"] = self.time_range

        try:
            resp = await http.get(
                self.base_url + "/search",
                params=params,
                timeout=outbound_timeout(),
                extensions={SSRF_ALLOW_PRIVATE_EXTENSION: True},
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 403:
                raise RuntimeError(
                    "SearXNG returned 403 Forbidden - make sure 'json' is in "
                    "search.formats in your settings.yml. See "
                    "https://docs.searxng.org/admin/settings/settings_search.html"
                ) from exc
            raise

        data = resp.json()
        raw_results = (data.get("results") or [])[:limit]

        out: list[SearchResult] = []
        for r in raw_results:
            url = r.get("url", "")
            if not url:
                continue
            published_at = _parse_published_at(r.get("publishedDate"))
            out.append(
                SearchResult(
                    url=url,
                    title=r.get("title", ""),
                    snippet=r.get("content", "") or "",
                    score=r.get("score"),
                    published_at=published_at,
                    engine=r.get("engine", ""),
                    raw=r,
                )
            )
        return out
