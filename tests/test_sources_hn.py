"""Hacker News source tests."""

from __future__ import annotations

import httpx
import pytest
import respx

from glean.sources.hn import HNSource

pytestmark = pytest.mark.asyncio


_HN_RESPONSE = {
    "hits": [
        {
            "objectID": "12345",
            "title": "Show HN: Cool project",
            "url": "https://example.com/cool",
            "author": "alice",
            "points": 150,
            "num_comments": 42,
            "created_at": "2024-01-15T12:00:00.000Z",
            "created_at_i": 1705320000,
            "_tags": ["story", "show_hn"],
        },
        {
            "objectID": "67890",
            "title": "Ask HN: question",
            "url": None,
            "author": "bob",
            "points": 0,
            "num_comments": 10,
            "created_at": "2024-01-15T11:00:00.000Z",
            "created_at_i": 1705316400,
            "story_text": "<p>Ask body</p>",
            "_tags": ["story", "ask_hn"],
        },
    ]
}


@respx.mock
async def test_hn_fetch_parses_results(fetch_context):
    respx.get("https://hn.algolia.com/api/v1/search_by_date").mock(
        return_value=httpx.Response(200, json=_HN_RESPONSE)
    )
    src = HNSource(query="show hn", min_points=10)

    items = await src.fetch(fetch_context)

    assert len(items) == 2
    assert items[0].title == "Show HN: Cool project"
    assert items[0].canonical_url == "https://example.com/cool"
    assert items[0].source_type == "hn"
    assert items[0].source_name == "HN: show hn"
    assert items[0].score == 150.0
    assert items[0].published_at is not None
    assert items[1].canonical_url == "https://news.ycombinator.com/item?id=67890"
    assert items[1].body == "Ask body"
    assert items[1].score is None


@respx.mock
async def test_hn_min_points_filter_is_sent_to_algolia(fetch_context):
    route = respx.get("https://hn.algolia.com/api/v1/search_by_date").mock(
        return_value=httpx.Response(200, json={"hits": []})
    )
    src = HNSource(query="show hn", min_points=100)

    await src.fetch(fetch_context)

    params = route.calls.last.request.url.params
    assert params["query"] == "show hn"
    assert params["tags"] == "story"
    assert "points>=100" in params["numericFilters"]


@respx.mock
async def test_hn_uses_window_hours_and_max_items_in_request(fetch_context):
    route = respx.get("https://hn.algolia.com/api/v1/search_by_date").mock(
        return_value=httpx.Response(200, json={"hits": []})
    )
    src = HNSource(query="ai", tags="story,show_hn", window_hours=12, max_items=7)

    await src.fetch(fetch_context)

    params = route.calls.last.request.url.params
    assert "created_at_i>" in params["numericFilters"]
    assert params["hitsPerPage"] == "7"
    assert params["tags"] == "story,show_hn"


@respx.mock
async def test_hn_handles_empty_response(fetch_context):
    respx.get("https://hn.algolia.com/api/v1/search_by_date").mock(
        return_value=httpx.Response(200, json={"hits": []})
    )
    src = HNSource(query="rare-search")

    items = await src.fetch(fetch_context)

    assert items == []


@respx.mock
async def test_hn_uses_story_fields_and_skips_missing_title(fetch_context):
    respx.get("https://hn.algolia.com/api/v1/search_by_date").mock(
        return_value=httpx.Response(
            200,
            json={
                "hits": [
                    {
                        "objectID": "1",
                        "story_title": "Story title",
                        "story_url": "https://example.com/story",
                        "comment_text": "<p>Comment body</p>",
                    },
                    {"objectID": "2", "url": "https://example.com/no-title"},
                ]
            },
        )
    )
    src = HNSource(tags="comment")

    items = await src.fetch(fetch_context)

    assert len(items) == 1
    assert items[0].title == "Story title"
    assert items[0].canonical_url == "https://example.com/story"
    assert items[0].body == "Comment body"
    assert items[0].published_at is None
    assert items[0].source_name == "HN: comment"


@respx.mock
async def test_hn_raises_on_http_error(fetch_context):
    respx.get("https://hn.algolia.com/api/v1/search_by_date").mock(return_value=httpx.Response(503))
    src = HNSource(query="ai")

    with pytest.raises(httpx.HTTPStatusError):
        await src.fetch(fetch_context)
