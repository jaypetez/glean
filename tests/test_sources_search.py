"""Web search source tests."""

from __future__ import annotations

import json
from datetime import datetime

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


@respx.mock
async def test_legacy_searxng_url_is_ignored_for_non_searxng(fetch_context, monkeypatch):
    monkeypatch.setenv("BRAVE_API_KEY", "brave-key")
    respx.get("https://api.search.brave.com/res/v1/web/search").mock(
        return_value=httpx.Response(200, json={"web": {"results": []}})
    )
    src = SearchSource(
        query="test",
        engine="brave",
        searxng_url="https://searxng.example.com",
    )

    assert await src.fetch(fetch_context) == []


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
                    {
                        "title": "Result 1",
                        "url": "https://example.com/1",
                        "content": "snippet 1",
                        "publishedDate": "2024-01-15T08:00:00+02:00",
                    },
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
    assert items[0].published_at == datetime.fromisoformat("2024-01-15T08:00:00+02:00")
    params = route.calls.last.request.url.params
    assert params["q"] == "test"
    assert params["format"] == "json"
    assert "categories" not in params
    assert "safesearch" not in params


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


async def test_search_engine_defaults_to_env(fetch_context, monkeypatch):
    monkeypatch.setenv("SEARCH_ENGINE", "searxng")
    monkeypatch.delenv("SEARXNG_URL", raising=False)
    src = SearchSource(query="test")

    with pytest.raises(RuntimeError, match="SEARXNG_URL"):
        await src.fetch(fetch_context)


# --- Tests for new backends added to the plugin layer ---


@respx.mock
async def test_serper_backend_parses_organic_results(fetch_context, monkeypatch):
    monkeypatch.setenv("SERPER_API_KEY", "serper-key-123")
    respx.post("https://google.serper.dev/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "organic": [
                    {"title": "Result 1", "link": "https://ex.com/1", "snippet": "snip 1"},
                    {"title": "Result 2", "link": "https://ex.com/2", "snippet": "snip 2"},
                    {"title": "No link"},
                ],
            },
        )
    )
    src = SearchSource(query="test", engine="serper", limit=5)
    items = await src.fetch(fetch_context)
    assert len(items) == 2
    assert items[0].title == "Result 1"
    assert items[0].canonical_url == "https://ex.com/1"
    assert items[0].source_name == "serper:test"


async def test_serper_requires_api_key(fetch_context, monkeypatch):
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    src = SearchSource(query="test", engine="serper")
    with pytest.raises(RuntimeError, match="SERPER_API_KEY"):
        await src.fetch(fetch_context)


@respx.mock
async def test_exa_backend_parses_results(fetch_context, monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "exa-key")
    respx.post("https://api.exa.ai/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "url": "https://ex.com/1",
                        "title": "Exa 1",
                        "score": 0.9,
                        "publishedDate": "2024-01-15T08:00:00+02:00",
                        "highlights": ["important snippet here"],
                    },
                    {"url": "https://ex.com/2", "title": "Exa 2", "text": "full text body"},
                ]
            },
        )
    )
    src = SearchSource(query="vector dbs", engine="exa", limit=5)
    items = await src.fetch(fetch_context)
    assert len(items) == 2
    assert items[0].score == 0.9
    assert items[0].body == "important snippet here"
    assert items[0].published_at == datetime.fromisoformat("2024-01-15T08:00:00+02:00")
    assert items[1].body == "full text body"


@respx.mock
async def test_exa_with_text_option_sends_contents_param(fetch_context, monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "exa-key")
    route = respx.post("https://api.exa.ai/search").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    src = SearchSource(query="q", engine="exa", include_text=True, search_type="neural")
    await src.fetch(fetch_context)
    body = json.loads(route.calls.last.request.content)
    assert body["contents"] == {"text": True, "highlights": True}
    assert body["type"] == "neural"


async def test_exa_requires_api_key(fetch_context, monkeypatch):
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    src = SearchSource(query="test", engine="exa")
    with pytest.raises(RuntimeError, match="EXA_API_KEY"):
        await src.fetch(fetch_context)


@respx.mock
async def test_mwmbl_backend_parses_results(fetch_context):
    respx.get(host="api.mwmbl.org").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {"url": "https://ex.com/1", "title": "MW 1", "extract": "extract 1"},
                    {"url": "https://ex.com/2", "title": "MW 2", "extract": "extract 2"},
                ]
            },
        )
    )
    src = SearchSource(query="open source", engine="mwmbl", limit=10)
    items = await src.fetch(fetch_context)
    assert len(items) == 2
    assert items[0].body == "extract 1"
    assert items[0].source_name == "mwmbl:open source"


@respx.mock
async def test_mwmbl_handles_list_response(fetch_context):
    """Some MWMBL versions return a bare list instead of {results: [...]}."""
    respx.get(host="api.mwmbl.org").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"url": "https://ex.com/1", "title": "MW 1", "extract": "extract 1"},
            ],
        )
    )
    src = SearchSource(query="q", engine="mwmbl")
    items = await src.fetch(fetch_context)
    assert len(items) == 1


@respx.mock
async def test_searxng_passes_categories_and_time_range(fetch_context):
    respx.get(host="searxng.test").mock(
        return_value=httpx.Response(
            200,
            json={"results": [{"url": "https://ex.com/1", "title": "T1", "content": "C1"}]},
        )
    )
    src = SearchSource(
        query="llms",
        engine="searxng",
        base_url="http://searxng.test",
        categories="news",
        time_range="day",
    )
    items = await src.fetch(fetch_context)
    req = respx.calls.last.request
    assert req.url.params["categories"] == "news"
    assert req.url.params["time_range"] == "day"
    assert req.url.params["format"] == "json"
    assert len(items) == 1


@respx.mock
async def test_searxng_403_raises_helpful_error(fetch_context):
    """SearXNG returns 403 if json format isn't enabled in settings.yml."""
    respx.get(host="searxng.test").mock(return_value=httpx.Response(403, text="format not enabled"))
    src = SearchSource(query="test", engine="searxng", base_url="http://searxng.test")
    with pytest.raises(RuntimeError, match="403 Forbidden"):
        await src.fetch(fetch_context)


async def test_unknown_engine_raises():
    with pytest.raises(ValueError, match="unknown search engine"):
        SearchSource(query="q", engine="nonexistent_engine_xyz")
