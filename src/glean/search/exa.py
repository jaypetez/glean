"""Exa.ai (formerly Metaphor) semantic search backend."""
from __future__ import annotations

import os
from contextlib import suppress
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar

from glean.search.base import SearchResult
from glean.search.registry import register_backend

if TYPE_CHECKING:
    import httpx


def _parse_published_at(value: str | None) -> datetime | None:
    if not value:
        return None
    timestamp = value[:-1] + "+00:00" if value.endswith("Z") else value
    with suppress(ValueError):
        parsed = datetime.fromisoformat(timestamp)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


@register_backend("exa")
class ExaBackend:
    name: ClassVar[str] = "exa"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        search_type: str = "auto",
        include_text: bool = False,
    ) -> None:
        self._api_key = api_key or os.environ.get("EXA_API_KEY")
        self.search_type = search_type
        self.include_text = include_text

    async def search(
        self,
        query: str,
        *,
        http: httpx.AsyncClient,
        limit: int = 10,
    ) -> list[SearchResult]:
        if not self._api_key:
            raise RuntimeError("EXA_API_KEY is not set")
        payload: dict[str, Any] = {
            "query": query,
            "numResults": limit,
            "type": self.search_type,
        }
        if self.include_text:
            payload["contents"] = {"text": True, "highlights": True}

        resp = await http.post(
            "https://api.exa.ai/search",
            headers={"x-api-key": self._api_key, "Content-Type": "application/json"},
            json=payload,
            timeout=30.0,
        )
        resp.raise_for_status()
        results = resp.json().get("results") or []
        out: list[SearchResult] = []
        for r in results:
            url = r.get("url", "")
            if not url:
                continue
            published_at = _parse_published_at(r.get("publishedDate"))
            snippet = r.get("text") or " ... ".join(r.get("highlights") or []) or ""
            out.append(
                SearchResult(
                    url=url,
                    title=r.get("title", ""),
                    snippet=snippet,
                    score=r.get("score"),
                    published_at=published_at,
                    raw=r,
                )
            )
        return out
