from __future__ import annotations

import re
import time
from datetime import UTC, datetime
from typing import ClassVar

from glean.sources.base import FetchContext, Item
from glean.sources.registry import register_source

_ALGOLIA = "https://hn.algolia.com/api/v1/search_by_date"
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


@register_source("hn")
class HNSource:
    """Hacker News via Algolia search-by-date endpoint."""

    type: ClassVar[str] = "hn"

    def __init__(
        self,
        query: str = "",
        *,
        tags: str = "story",
        min_points: int = 0,
        max_items: int = 50,
        window_hours: int = 24,
    ) -> None:
        self.query = query
        self.tags = tags
        self.min_points = min_points
        self.max_items = max_items
        self.window_hours = window_hours

    async def fetch(self, ctx: FetchContext) -> list[Item]:
        since_ts = int(time.time()) - self.window_hours * 3600
        numeric_filters = [f"created_at_i>{since_ts}"]
        if self.min_points > 0:
            numeric_filters.append(f"points>={self.min_points}")

        params = {
            "query": self.query,
            "tags": self.tags,
            "numericFilters": ",".join(numeric_filters),
            "hitsPerPage": str(self.max_items),
        }
        resp = await ctx.http.get(_ALGOLIA, params=params, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()

        items: list[Item] = []
        for hit in data.get("hits", []):
            object_id = hit.get("objectID")
            title = (hit.get("title") or hit.get("story_title") or "").strip()
            url = (hit.get("url") or hit.get("story_url") or "").strip()
            if not url and object_id:
                url = f"https://news.ycombinator.com/item?id={object_id}"
            if not title:
                continue

            body = hit.get("story_text") or hit.get("comment_text") or ""
            published_at: datetime | None = None
            created_at_i = hit.get("created_at_i")
            if created_at_i:
                published_at = datetime.fromtimestamp(int(created_at_i), tz=UTC)

            items.append(
                Item(
                    canonical_url=url,
                    title=title,
                    body=_strip_html(body),
                    source_type="hn",
                    source_name=f"HN: {self.query or self.tags}",
                    published_at=published_at,
                    score=float(hit.get("points") or 0) or None,
                    raw=hit,
                )
            )
        return items


def _strip_html(html: str) -> str:
    if not html:
        return ""
    text = _TAG_RE.sub(" ", html)
    return _WS_RE.sub(" ", text).strip()
