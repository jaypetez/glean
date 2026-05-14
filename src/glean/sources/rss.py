from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, ClassVar

import feedparser

from glean.security.ssrf import validate_url
from glean.sources._fetch import DEFAULT_MAX_BYTES, follow_with_validation
from glean.sources.base import FetchContext, Item
from glean.sources.registry import register_source

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


@register_source("rss")
class RSSSource:
    type: ClassVar[str] = "rss"

    def __init__(
        self,
        url: str,
        *,
        name: str | None = None,
        max_response_bytes: int = DEFAULT_MAX_BYTES,
    ) -> None:
        self.url = validate_url(url)
        self.name = name or url
        self.max_response_bytes = max_response_bytes

    async def fetch(self, ctx: FetchContext) -> list[Item]:
        etag, last_modified = await ctx.state.get_etag(self.url)
        headers: dict[str, str] = {"User-Agent": "glean/0.1"}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified

        resp = await follow_with_validation(
            ctx.http,
            self.url,
            headers=headers,
            max_bytes=self.max_response_bytes,
        )
        if resp.status_code == 304:
            return []
        resp.raise_for_status()

        parsed = feedparser.parse(resp.content)
        new_etag = resp.headers.get("ETag")
        new_lm = resp.headers.get("Last-Modified")
        if new_etag or new_lm:
            await ctx.state.set_etag(self.url, new_etag, new_lm)

        items: list[Item] = []
        for entry in parsed.entries:
            url = (entry.get("link") or "").strip()
            title = (entry.get("title") or "").strip()
            if not url and not title:
                continue
            summary = entry.get("summary") or entry.get("description")
            body = ""
            if "content" in entry and entry.content:
                body = entry.content[0].get("value") or ""
            elif summary:
                body = summary

            published_at: datetime | None = None
            for key in ("published_parsed", "updated_parsed"):
                pp = entry.get(key)
                if pp:
                    try:
                        y, mo, d, h, mi, s = (int(x) for x in pp[:6])
                        published_at = datetime(y, mo, d, h, mi, s, tzinfo=UTC)
                        break
                    except (TypeError, ValueError):
                        pass

            items.append(
                Item(
                    canonical_url=url,
                    title=title,
                    body=_strip_html(body),
                    summary=_strip_html(summary) if summary else None,
                    source_type="rss",
                    source_name=parsed.feed.get("title") or self.name,
                    published_at=published_at,
                    raw=dict(entry) if isinstance(entry, dict) else {"_raw": str(entry)},
                )
            )
        return items


def _strip_html(html: Any) -> str:
    if not html:
        return ""
    text = _TAG_RE.sub(" ", str(html))
    return _WS_RE.sub(" ", text).strip()
