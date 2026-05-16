from __future__ import annotations

from typing import ClassVar

import trafilatura

from glean.logging import get_logger
from glean.security.scrub import scrub
from glean.security.ssrf import validate_url
from glean.sources._fetch import DEFAULT_MAX_BYTES, follow_with_validation
from glean.sources.base import FetchContext, Item
from glean.sources.registry import register_source

logger = get_logger(__name__)


@register_source("scraper")
class ScraperSource:
    """Fetch a fixed list of article URLs and extract full text via trafilatura."""

    type: ClassVar[str] = "scraper"

    def __init__(self, urls: list[str], *, max_response_bytes: int = DEFAULT_MAX_BYTES) -> None:
        if not urls:
            raise ValueError("scraper source requires at least one url")
        self.urls = [validate_url(url) for url in urls]
        self.max_response_bytes = max_response_bytes

    async def fetch(self, ctx: FetchContext) -> list[Item]:
        items: list[Item] = []
        for url in self.urls:
            try:
                resp = await follow_with_validation(
                    ctx.http,
                    url,
                    headers={"User-Agent": "glean/0.1"},
                    max_bytes=self.max_response_bytes,
                )
                resp.raise_for_status()
            except Exception as exc:
                logger.warning("scraper_fetch_failed", url=url, err=scrub(str(exc))[:500])
                continue

            extracted = trafilatura.extract(
                resp.text,
                include_comments=False,
                include_tables=False,
                favor_recall=True,
                url=url,
            )
            metadata = trafilatura.extract_metadata(resp.text) if extracted else None
            title = (metadata.title if metadata else None) or url
            body = extracted or ""

            items.append(
                Item(
                    canonical_url=url,
                    title=title,
                    body=body,
                    summary=None,
                    source_type="scraper",
                    source_name=url,
                )
            )
        return items
