"""Web search source tests."""
from __future__ import annotations

import json

import httpx
import pytest
import respx

from glean.sources.search import SearchSource

pytestmark = pytest.mark.asyncio


@respx.mock
async def test_brave_engine_parses_web_results(fetch_context, monkeypatch):
    monkeypatch.setenv("BRAVE_API_KEY", "brave-key")
    route = respx.get("https://api.search.brave.com/res/v1/web/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "web": {
                    "results": [
                        {
                            "title": "Result 1",
                            "url": "https://example.com/1",
                            "description": "snippet 1",
                        },
                        {"title": "Missing URL", "description": "skip me"},
                    ]
                }
            },
        )
    )
    src = SearchSource(query="test", engine="brave", limit=3)

    items = await src.fetch(fetch_context)

    assert len(items) == 1
    assert items[0].title == "Result 1"
    assert items[0].canonical_url == "https://example.com/1"
    assert items[0].body == "snippet 1"
    assert items[0].source_type == "search"
    assert items[0].source_name == "brave:test"
    request = route.calls.last.request
    assert request.headers["X-Subscription-Token"] == "brave-key"
    assert request.url.params["q"] == "test"
    assert request.url.params["count"] == "3"


async def test_brave_engine_requires_api_key(fetch_context):
    src = SearchSource(query="test", engine="brave")

    with pytest.raises(RuntimeError, match="BRAVE_API_KEY"):
        await src.fetch(fetch_context)


@respx.mock
async def test_tavily_engine_parses_results(fetch_context, monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tavily-key")
    route = respx.post("https://api.tavily.com/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Tavily 1",
                        "url": "https://example.com/t1",
                        "content": "tavily snippet",
                    },
                    {"title": "Missing URL", "content": "skip me"},
                ]
            },
        )
    )
    src = SearchSource(query="python", engine="tavily", limit=2)

    items = await src.fetch(fetch_context)

    assert len(items) == 1
    assert items[0].title == "Tavily 1"
    assert items[0].canonical_url == "https://example.com/t1"
    assert items[0].body == "tavily snippet"
    assert items[0].source_name == "tavily:python"
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "api_key": "tavily-key",
        "query": "python",
        "max_results": 2,
        "search_depth": "basic",
    }


async def test_tavily_engine_requires_api_key(fetch_context):
    src = SearchSource(query="test", engine="tavily")

    with pytest.raises(RuntimeError, match="TAVILY_API_KEY"):
        await src.fetch(fetch_context)


@respx.mock
async def test_searxng_engine_parses_and_truncates_results(fetch_context):
    route = respx.get("https://searxng.example.com/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {"title": "Result 1", "url": "https://example.com/1", "content": "snippet 1"},
                    {"title": "Result 2", "url": "https://example.com/2", "content": "snippet 2"},
                    {"title": "Result 3", "url": "https://example.com/3", "content": "snippet 3"},
                ]
            },
        )
    )
    src = SearchSource(
        query="test",
        engine="searxng",
        limit=2,
        searxng_url="https://searxng.example.com/",
    )

    items = await src.fetch(fetch_context)

    assert [item.title for item in items] == ["Result 1", "Result 2"]
    assert items[0].source_type == "search"
    assert items[0].source_name == "searxng:test"
    assert route.calls.last.request.url.params["q"] == "test"
    assert route.calls.last.request.url.params["format"] == "json"


@respx.mock
async def test_searxng_engine_uses_env_url_and_skips_missing_urls(fetch_context, monkeypatch):
    monkeypatch.setenv("SEARXNG_URL", "https://searxng.example.com")
    respx.get("https://searxng.example.com/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {"title": "Missing URL", "content": "skip me"},
                    {"title": "Result", "url": "https://example.com", "content": "snippet"},
                ]
            },
        )
    )
    src = SearchSource(query="env", engine="searxng")

    items = await src.fetch(fetch_context)

    assert len(items) == 1
    assert items[0].canonical_url == "https://example.com"


async def test_searxng_engine_requires_url(fetch_context, monkeypatch):
    monkeypatch.delenv("SEARXNG_URL", raising=False)
    src = SearchSource(query="test", engine="searxng")

    with pytest.raises(RuntimeError, match="SEARXNG_URL"):
        await src.fetch(fetch_context)


async def test_unknown_search_engine_raises(fetch_context):
    src = SearchSource(query="test", engine="not-real")

    with pytest.raises(ValueError, match="unknown search engine"):
        await src.fetch(fetch_context)


async def test_search_engine_defaults_to_env(fetch_context, monkeypatch):
    monkeypatch.setenv("SEARCH_ENGINE", "searxng")
    monkeypatch.delenv("SEARXNG_URL", raising=False)
    src = SearchSource(query="test")

    with pytest.raises(RuntimeError, match="SEARXNG_URL"):
        await src.fetch(fetch_context)
