"""Scraper source tests."""
from __future__ import annotations

import httpx
import pytest
import respx

from glean.sources.scraper import ScraperSource

pytestmark = pytest.mark.asyncio


_HTML_PAGE = """
<!DOCTYPE html>
<html>
<head><title>Article Title</title></head>
<body>
  <article>
    <h1>Article Title</h1>
    <p>This is a long article paragraph with enough text to be extracted by trafilatura.
       It discusses interesting topics and has multiple sentences with substantive content.</p>
    <p>A second paragraph adds more body content for the extractor to find.</p>
  </article>
</body>
</html>
"""


@respx.mock
async def test_scraper_fetches_multiple_urls(fetch_context):
    respx.get("https://example.com/a").mock(return_value=httpx.Response(200, text=_HTML_PAGE))
    respx.get("https://example.com/b").mock(return_value=httpx.Response(200, text=_HTML_PAGE))
    src = ScraperSource(urls=["https://example.com/a", "https://example.com/b"])

    items = await src.fetch(fetch_context)

    assert len(items) == 2
    for item in items:
        assert item.source_type == "scraper"
        assert item.canonical_url.startswith("https://example.com/")
        assert item.source_name == item.canonical_url
        assert item.title in {"Article Title", item.canonical_url}


@respx.mock
async def test_scraper_sends_user_agent_and_follows_redirects(fetch_context):
    route = respx.get("https://example.com/a").mock(
        return_value=httpx.Response(200, text=_HTML_PAGE)
    )
    src = ScraperSource(urls=["https://example.com/a"])

    await src.fetch(fetch_context)

    assert route.calls.last.request.headers.get("User-Agent") == "glean/0.1"


@respx.mock
async def test_scraper_continues_after_url_failure(fetch_context):
    respx.get("https://example.com/good").mock(return_value=httpx.Response(200, text=_HTML_PAGE))
    respx.get("https://example.com/bad").mock(return_value=httpx.Response(500))
    src = ScraperSource(urls=["https://example.com/good", "https://example.com/bad"])

    items = await src.fetch(fetch_context)

    assert len(items) == 1
    assert items[0].canonical_url == "https://example.com/good"


@respx.mock
async def test_scraper_empty_response_yields_empty_body_item(fetch_context):
    respx.get("https://example.com/empty").mock(return_value=httpx.Response(200, text=""))
    src = ScraperSource(urls=["https://example.com/empty"])

    items = await src.fetch(fetch_context)

    assert len(items) == 1
    assert items[0].title == "https://example.com/empty"
    assert items[0].body == ""


async def test_scraper_requires_at_least_one_url():
    with pytest.raises(ValueError, match="at least one url"):
        ScraperSource(urls=[])
