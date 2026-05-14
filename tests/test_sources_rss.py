"""RSS source plugin tests."""
from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
import respx

from glean.sources._fetch import DEFAULT_MAX_BYTES, ResponseTooLargeError
from glean.sources.rss import RSSSource, _strip_html

pytestmark = pytest.mark.asyncio


_ATOM_FEED = '''<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Test Feed</title>
  <link href="https://example.com"/>
  <updated>2024-01-15T12:00:00Z</updated>
  <entry>
    <title>First post</title>
    <link href="https://example.com/1"/>
    <id>https://example.com/1</id>
    <updated>2024-01-15T12:00:00Z</updated>
    <published>2024-01-15T11:00:00Z</published>
    <summary>This is the first post summary.</summary>
    <content type="html">&lt;p&gt;Full HTML content here&lt;/p&gt;</content>
  </entry>
  <entry>
    <title>Second post</title>
    <link href="https://example.com/2"/>
    <id>https://example.com/2</id>
    <updated>2024-01-15T13:00:00Z</updated>
    <summary>Second post.</summary>
  </entry>
</feed>'''


_RSS_FEED = '''<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <title>RSS Test</title>
    <link>https://example.com</link>
    <item>
      <title>RSS item 1</title>
      <link>https://example.com/r1</link>
      <description>&lt;b&gt;HTML&lt;/b&gt; description</description>
      <pubDate>Mon, 15 Jan 2024 12:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>'''


async def test_rss_defaults_to_ten_mib_response_cap() -> None:
    src = RSSSource(url="https://example.com/feed")

    assert src.max_response_bytes == DEFAULT_MAX_BYTES


@respx.mock
async def test_rss_uses_configured_response_cap(fetch_context):
    respx.get("https://example.com/feed").mock(return_value=httpx.Response(200, content=b"abcde"))
    src = RSSSource(url="https://example.com/feed", max_response_bytes=4)

    with pytest.raises(ResponseTooLargeError, match="content-length 5 exceeds cap 4"):
        await src.fetch(fetch_context)


@respx.mock
async def test_rss_fetch_atom(fetch_context):
    respx.get("https://example.com/feed").mock(
        return_value=httpx.Response(
            200,
            content=_ATOM_FEED,
            headers={"Content-Type": "application/atom+xml"},
        )
    )
    src = RSSSource(url="https://example.com/feed")

    items = await src.fetch(fetch_context)

    assert len(items) == 2
    assert items[0].title == "First post"
    assert items[0].canonical_url == "https://example.com/1"
    assert items[0].source_type == "rss"
    assert items[0].source_name == "Test Feed"
    assert items[0].published_at == datetime(2024, 1, 15, 11, 0, 0, tzinfo=UTC)
    assert items[0].body == "Full HTML content here"
    assert items[0].summary == "This is the first post summary."
    assert items[1].body == "Second post."


@respx.mock
async def test_rss_fetch_rss20(fetch_context):
    respx.get("https://example.com/rss").mock(return_value=httpx.Response(200, content=_RSS_FEED))
    src = RSSSource(url="https://example.com/rss")

    items = await src.fetch(fetch_context)

    assert len(items) == 1
    assert items[0].title == "RSS item 1"
    assert items[0].source_name == "RSS Test"
    assert items[0].body == "HTML description"
    assert items[0].published_at == datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)


@respx.mock
async def test_rss_returns_empty_on_304(fetch_context):
    await fetch_context.state.set_etag("https://example.com/feed", "abc123", None)
    respx.get("https://example.com/feed").mock(return_value=httpx.Response(304))
    src = RSSSource(url="https://example.com/feed")

    items = await src.fetch(fetch_context)

    assert items == []


@respx.mock
async def test_rss_sends_etag_header_when_cached(fetch_context):
    await fetch_context.state.set_etag(
        "https://example.com/feed", "etag-1", "Mon, 15 Jan 2024 11:00:00 GMT"
    )
    route = respx.get("https://example.com/feed").mock(
        return_value=httpx.Response(200, content=_ATOM_FEED)
    )
    src = RSSSource(url="https://example.com/feed")

    await src.fetch(fetch_context)

    req = route.calls.last.request
    assert req.headers.get("If-None-Match") == "etag-1"
    assert req.headers.get("If-Modified-Since") == "Mon, 15 Jan 2024 11:00:00 GMT"
    assert req.headers.get("User-Agent") == "glean/0.1"


@respx.mock
async def test_rss_stores_new_etag(fetch_context):
    respx.get("https://example.com/feed").mock(
        return_value=httpx.Response(
            200,
            content=_ATOM_FEED,
            headers={"ETag": "new-etag", "Last-Modified": "Mon, 15 Jan 2024 14:00:00 GMT"},
        )
    )
    src = RSSSource(url="https://example.com/feed")

    await src.fetch(fetch_context)

    etag, last_mod = await fetch_context.state.get_etag("https://example.com/feed")
    assert etag == "new-etag"
    assert last_mod == "Mon, 15 Jan 2024 14:00:00 GMT"


@respx.mock
async def test_rss_raises_on_http_error(fetch_context):
    respx.get("https://example.com/feed").mock(return_value=httpx.Response(500))
    src = RSSSource(url="https://example.com/feed")

    with pytest.raises(httpx.HTTPStatusError):
        await src.fetch(fetch_context)


@respx.mock
async def test_rss_skips_entries_without_url_or_title(fetch_context):
    feed = '''<?xml version="1.0"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <title>Fallback Feed</title>
      <entry><title>OK</title><link href="https://example.com/x"/></entry>
      <entry></entry>
    </feed>'''
    respx.get("https://example.com/feed").mock(return_value=httpx.Response(200, content=feed))
    src = RSSSource(url="https://example.com/feed")

    items = await src.fetch(fetch_context)

    assert len(items) == 1
    assert items[0].title == "OK"
    assert items[0].canonical_url == "https://example.com/x"


@respx.mock
async def test_rss_uses_configured_name_when_feed_has_no_title(fetch_context):
    feed = '''<?xml version="1.0"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry><title>OK</title><link href="https://example.com/x"/></entry>
    </feed>'''
    respx.get("https://example.com/feed").mock(return_value=httpx.Response(200, content=feed))
    src = RSSSource(url="https://example.com/feed", name="Configured")

    items = await src.fetch(fetch_context)

    assert items[0].source_name == "Configured"


async def test_strip_html_handles_empty_values():
    assert _strip_html(None) == ""
    assert _strip_html("<p>Hello&nbsp; <b>world</b></p>") == "Hello&nbsp; world"
