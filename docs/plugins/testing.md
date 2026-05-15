---
title: Testing Plugins — glean
description: Test source, sink, LLM provider, and search backend plugins without calling real services.
---

# Testing Plugins

This page is for plugin authors who need a focused unit test before opening a PR. You can test a plugin with the existing fixtures and `respx`; no real tokens or network calls are needed.

## Test environment isolation

`tests/conftest.py` has an autouse fixture named `_isolate_env`. It removes API keys, bot tokens, database paths, auth toggles, and service URLs before every test, then points file sinks at the test temp directory.

Set only the environment variables your test needs with `monkeypatch.setenv`. Do not rely on local shell secrets.

## Mock HTTP with respx

Use `respx` for plugins that call HTTP APIs. This source test intercepts an RSS request, returns a fixture body, and asserts the normalized `Item` fields.

```python
from __future__ import annotations

import respx
from httpx import Response

from glean.sources.rss import RSSSource


async def test_rss_source_fetches_items(fetch_context) -> None:
    body = b"""
    <rss version="2.0">
      <channel>
        <title>Example Feed</title>
        <item>
          <title>Launch notes</title>
          <link>https://example.com/launch</link>
          <description>&lt;p&gt;New release&lt;/p&gt;</description>
        </item>
      </channel>
    </rss>
    """

    with respx.mock(assert_all_called=True) as router:
        router.get("https://example.com/feed.xml").mock(
            return_value=Response(200, content=body, headers={"ETag": "v1"})
        )

        source = RSSSource("https://example.com/feed.xml", name="Example")
        items = await source.fetch(fetch_context)

    assert len(items) == 1
    assert items[0].canonical_url == "https://example.com/launch"
    assert items[0].title == "Launch notes"
    assert items[0].body == "New release"
```

Run the file while you iterate:

```bash
uv run pytest tests/test_sources_rss.py -v
```

Expected output:

```text
tests/test_sources_rss.py::test_rss_source_fetches_items PASSED
```

## Register fakes in tests

`tests/test_runner.py` registers fake plugins with the same decorators as production plugins. Use this pattern when you need the pipeline, config loader, or registry behavior in scope.

```python
from __future__ import annotations

from glean.llm.registry import register_provider
from glean.sources.base import FetchContext, Item
from glean.sources.registry import register_source


@register_source("fake")
class FakeSource:
    type = "fake"

    def __init__(self, items: list[dict] | None = None) -> None:
        self.items = items or []

    async def fetch(self, ctx: FetchContext) -> list[Item]:
        return [
            Item(
                canonical_url=row.get("url", ""),
                title=row.get("title", ""),
                body=row.get("body", ""),
                source_type="fake",
                source_name="fake",
            )
            for row in self.items
        ]


@register_provider("fake")
class FakeLLM:
    name = "fake"

    def __init__(self, **_: object) -> None:
        self.model = "fake"

    async def rank(self, item: Item, prompt: str) -> float:
        return 0.9

    async def summarize(self, item: Item, prompt: str) -> str:
        return f"summary of {item.title}"

    async def digest(self, items: list[Item], prompt: str) -> str:
        return prompt

    async def aclose(self) -> None:
        pass
```

The decorator call mutates the in-memory registry for the test process. Use unique names if the fake behavior differs across files.

## Isolate state with tmp_db

Use `tmp_db` when a test opens `StateStore` directly. Use `state_store` when you need an already-open store, and `fetch_context` when a source needs both `httpx.AsyncClient` and state.

```python
from __future__ import annotations

from pathlib import Path

from glean.state.store import StateStore


async def test_marks_seen(tmp_db: Path) -> None:
    store = StateStore(tmp_db)
    await store.open()
    try:
        await store.set_bootstrapped("plugin-test")
        assert await store.is_bootstrapped("plugin-test")
    finally:
        await store.close()
```

Expected output when run with `uv run pytest tests/test_state_store.py::test_marks_seen -v`:

```text
tests/test_state_store.py::test_marks_seen PASSED
```

## Coverage gates

CI enforces project coverage at 80% or higher. Codecov also reports patch coverage and expects at least 70% for changed code.

A plugin PR should cover success, empty responses, malformed rows, and upstream HTTP errors. For network plugins, assert that no unmocked requests escape `respx`.
