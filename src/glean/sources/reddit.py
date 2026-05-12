from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar

from glean.sources.base import FetchContext, Item
from glean.sources.registry import register_source


@register_source("reddit")
class RedditSource:
    """Read public Reddit JSON listings; no auth required."""

    type: ClassVar[str] = "reddit"

    def __init__(
        self,
        subreddit: str,
        *,
        sort: str = "top",
        timeframe: str = "day",
        limit: int = 25,
    ) -> None:
        self.subreddit = subreddit.lstrip("r/").lstrip("/")
        self.sort = sort
        self.timeframe = timeframe
        self.limit = limit

    async def fetch(self, ctx: FetchContext) -> list[Item]:
        url = f"https://www.reddit.com/r/{self.subreddit}/{self.sort}.json"
        params: dict[str, str] = {"limit": str(self.limit), "raw_json": "1"}
        if self.sort in ("top", "controversial"):
            params["t"] = self.timeframe

        resp = await ctx.http.get(
            url,
            params=params,
            headers={"User-Agent": "glean/0.1 (+https://github.com/jaypetez/glean)"},
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()

        items: list[Item] = []
        for child in data.get("data", {}).get("children", []):
            d = child.get("data") or {}
            title = (d.get("title") or "").strip()
            if not title:
                continue
            permalink = d.get("permalink") or ""
            link = f"https://www.reddit.com{permalink}" if permalink else d.get("url", "")
            body = d.get("selftext") or ""

            published_at: datetime | None = None
            created_utc = d.get("created_utc")
            if created_utc:
                published_at = datetime.fromtimestamp(float(created_utc), tz=UTC)

            items.append(
                Item(
                    canonical_url=link,
                    title=title,
                    body=body,
                    summary=None,
                    source_type="reddit",
                    source_name=f"r/{self.subreddit}",
                    published_at=published_at,
                    score=float(d.get("ups") or 0) or None,
                    raw=d,
                )
            )
        return items
