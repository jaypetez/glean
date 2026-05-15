"""Reddit source tests."""

from __future__ import annotations

import httpx
import pytest
import respx

from glean.sources.reddit import RedditSource

pytestmark = pytest.mark.asyncio


_REDDIT_RESPONSE = {
    "data": {
        "children": [
            {
                "data": {
                    "title": "First post",
                    "url": "https://example.com/1",
                    "permalink": "/r/test/comments/abc/first/",
                    "selftext": "Post body text",
                    "author": "alice",
                    "ups": 100,
                    "num_comments": 5,
                    "created_utc": 1705320000,
                    "subreddit": "test",
                }
            },
            {
                "data": {
                    "title": "[deleted]",
                    "url": "",
                    "permalink": "/r/test/comments/def/deleted/",
                    "selftext": "[deleted]",
                    "author": "[deleted]",
                    "ups": 0,
                    "num_comments": 0,
                    "created_utc": 1705316400,
                    "subreddit": "test",
                }
            },
            {"data": {"title": "", "url": "https://example.com/missing-title"}},
        ]
    }
}


@respx.mock
async def test_reddit_fetch_parses_listing(fetch_context):
    respx.get("https://www.reddit.com/r/test/top.json").mock(
        return_value=httpx.Response(200, json=_REDDIT_RESPONSE)
    )
    src = RedditSource(subreddit="test")

    items = await src.fetch(fetch_context)

    assert len(items) == 2
    assert items[0].title == "First post"
    assert items[0].canonical_url == "https://www.reddit.com/r/test/comments/abc/first/"
    assert items[0].body == "Post body text"
    assert items[0].source_type == "reddit"
    assert items[0].source_name == "r/test"
    assert items[0].score == 100.0
    assert items[0].published_at is not None
    assert items[1].title == "[deleted]"
    assert items[1].score is None


@respx.mock
async def test_reddit_sends_user_agent(fetch_context):
    route = respx.get("https://www.reddit.com/r/test/top.json").mock(
        return_value=httpx.Response(200, json={"data": {"children": []}})
    )
    src = RedditSource(subreddit="test")

    await src.fetch(fetch_context)

    ua = route.calls.last.request.headers.get("User-Agent", "")
    assert "glean" in ua.lower()


@respx.mock
async def test_reddit_url_includes_sort_and_timeframe(fetch_context):
    route = respx.get("https://www.reddit.com/r/LocalLLaMA/top.json").mock(
        return_value=httpx.Response(200, json={"data": {"children": []}})
    )
    src = RedditSource(subreddit="r/LocalLLaMA", sort="top", timeframe="day", limit=5)

    await src.fetch(fetch_context)

    request = route.calls.last.request
    assert request.url.params["limit"] == "5"
    assert request.url.params["raw_json"] == "1"
    assert request.url.params["t"] == "day"


@respx.mock
async def test_reddit_omits_timeframe_for_new_sort(fetch_context):
    route = respx.get("https://www.reddit.com/r/test/new.json").mock(
        return_value=httpx.Response(200, json={"data": {"children": []}})
    )
    src = RedditSource(subreddit="/test", sort="new", timeframe="week")

    await src.fetch(fetch_context)

    assert "t" not in route.calls.last.request.url.params


@respx.mock
async def test_reddit_handles_empty_listing(fetch_context):
    respx.get("https://www.reddit.com/r/test/top.json").mock(
        return_value=httpx.Response(200, json={"data": {"children": []}})
    )
    src = RedditSource(subreddit="test")

    items = await src.fetch(fetch_context)

    assert items == []


@respx.mock
async def test_reddit_falls_back_to_post_url_without_permalink(fetch_context):
    respx.get("https://www.reddit.com/r/test/top.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "children": [
                        {
                            "data": {
                                "title": "External link",
                                "url": "https://example.com/out",
                                "selftext": "",
                            }
                        }
                    ]
                }
            },
        )
    )
    src = RedditSource(subreddit="test")

    items = await src.fetch(fetch_context)

    assert items[0].canonical_url == "https://example.com/out"
    assert items[0].published_at is None


@respx.mock
async def test_reddit_raises_on_http_error(fetch_context):
    respx.get("https://www.reddit.com/r/test/top.json").mock(return_value=httpx.Response(429))
    src = RedditSource(subreddit="test")

    with pytest.raises(httpx.HTTPStatusError):
        await src.fetch(fetch_context)
