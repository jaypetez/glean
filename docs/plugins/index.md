---
title: "Plugin Authoring — glean Plugins"
description: Add your own source, sink, LLM provider, or search backend in a single file.
---

# Plugin Authoring

Glean has 4 plugin layers, all using the same registration pattern: write a file, decorate with `@register_*`, add an import to `_import_builtins()`. That's the entire wiring.

| Plugin | Decorator | Protocol | Smallest example |
|---|---|---|---|
| **[Source](source.md)** | `@register_source("type")` | `async fetch(ctx) -> list[Item]` | `sources/rss.py` |
| **[Sink](sink.md)** | `@register_sink("type")` | `async send(ctx) -> None` | `sinks/telegram.py` |
| **[LLM Provider](llm.md)** | `@register_provider("name")` | `rank` / `summarize` / `digest` / `extract` | `llm/ollama_provider.py` |
| **[Search Backend](search.md)** | `@register_backend("name")` | `async search(query, *, http, limit)` | `search/searxng.py` |

## 30-second scaffold

Use this walkthrough when you add a plugin. Start with the layer you need, then keep the constructor arguments aligned with the YAML shape users will write.

=== "Source"

    ```python
    from __future__ import annotations

    from typing import ClassVar

    from glean.sources.base import FetchContext, Item
    from glean.sources.registry import register_source


    @register_source("my_source")
    class MySource:
        type: ClassVar[str] = "my_source"

        def __init__(self, *, topic: str, limit: int = 10) -> None:
            self.topic = topic
            self.limit = limit

        async def fetch(self, ctx: FetchContext) -> list[Item]:
            resp = await ctx.http.get("https://example.com/feed", params={"q": self.topic})
            resp.raise_for_status()
            rows = resp.json()["items"]
            return [
                Item(
                    canonical_url=row["url"],
                    title=row["title"],
                    body=row.get("body", ""),
                    source_type=self.type,
                    source_name=f"my_source:{self.topic}",
                    raw=row,
                )
                for row in rows[: self.limit]
            ]
    ```

=== "Sink"

    ```python
    from __future__ import annotations

    from typing import ClassVar

    import httpx

    from glean.sinks.base import SendContext
    from glean.sinks.registry import register_sink


    @register_sink("my_sink")
    class MySink:
        type: ClassVar[str] = "my_sink"

        def __init__(self, *, webhook_url: str, required: bool = True) -> None:
            self.webhook_url = webhook_url
            self.required = required
            self._http = httpx.AsyncClient(timeout=30.0)

        async def send(self, ctx: SendContext) -> None:
            for message in ctx.messages:
                resp = await self._http.post(self.webhook_url, json={"text": message})
                resp.raise_for_status()

        async def aclose(self) -> None:
            await self._http.aclose()
    ```

=== "LLM Provider"

    ```python
    from __future__ import annotations

    from typing import Any, ClassVar

    from glean.llm.common import parse_score
    from glean.llm.registry import register_provider
    from glean.sources.base import Item


    @register_provider("my_llm")
    class MyLLMProvider:
        name: ClassVar[str] = "my_llm"

        def __init__(self, *, model: str, api_key: str | None = None) -> None:
            self.model = model
            self.api_key = api_key

        async def rank(self, item: Item, prompt: str) -> float:
            return parse_score(await self._complete(prompt, item.body, max_tokens=16))

        async def summarize(self, item: Item, prompt: str) -> str:
            return await self._complete(prompt, item.body, max_tokens=256)

        async def digest(self, items: list[Item], prompt: str) -> str:
            body = "\n".join(item.title for item in items)
            return await self._complete(prompt, body, max_tokens=128)

        async def extract(
            self,
            item: Item,
            prompt: str,
            output_schema: dict[str, Any],
            *,
            system_prompt: str | None = None,
        ) -> dict[str, Any]:
            return {}

        async def aclose(self) -> None:
            pass
    ```

=== "Search Backend"

    ```python
    from __future__ import annotations

    from typing import TYPE_CHECKING, ClassVar

    from glean.search.base import SearchResult
    from glean.search.registry import register_backend

    if TYPE_CHECKING:
        import httpx


    @register_backend("my_search")
    class MySearchBackend:
        name: ClassVar[str] = "my_search"

        def __init__(self, *, api_key: str | None = None) -> None:
            self.api_key = api_key

        async def search(
            self,
            query: str,
            *,
            http: httpx.AsyncClient,
            limit: int = 10,
        ) -> list[SearchResult]:
            resp = await http.get(
                "https://search.example.com/api",
                params={"q": query, "limit": limit},
                timeout=30.0,
            )
            resp.raise_for_status()
            return [
                SearchResult(url=row["url"], title=row["title"], snippet=row.get("snippet", ""))
                for row in resp.json()["results"][:limit]
                if row.get("url")
            ]
    ```

After the file exists, add one import to the matching registry:

```python
def _import_builtins() -> None:
    from glean.sources import my_source  # noqa: F401
```

## Once your plugin works

- Write a [unit test](testing.md) using `respx` to mock the network.
- Add an entry to `feeds.example.yaml` showing the plugin in use.
- Open a PR — see [Publishing](publishing.md).
