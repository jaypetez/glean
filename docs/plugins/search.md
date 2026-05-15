---
title: "Writing a Search Backend — glean Plugins"
description: Implement and register a custom web search backend for glean.
---

# Authoring Search Backends

A **Search Backend** is a pluggable web search provider used by the `search`
source. Backends mirror the [Source](source.md), [LLM Provider](llm.md), and
[Sink](sink.md) plugin layers.

## The protocol

```python
# src/glean/search/base.py
@runtime_checkable
class SearchBackend(Protocol):
    name: ClassVar[str]

    async def search(
        self,
        query: str,
        *,
        http: httpx.AsyncClient,
        limit: int = 10,
    ) -> list[SearchResult]: ...
```

`SearchResult` is the normalized result shape:

```python
@dataclass(frozen=True, slots=True)
class SearchResult:
    url: str
    title: str
    snippet: str
    score: float | None = None
    published_at: datetime | None = None
    engine: str = ""           # upstream engine name (SearXNG fills this)
    raw: dict[str, Any] = field(default_factory=dict)
```

## Writing a backend

```python
# src/glean/search/myengine.py
from __future__ import annotations
from typing import TYPE_CHECKING, ClassVar

from glean.search.base import SearchResult
from glean.search.registry import register_backend

if TYPE_CHECKING:
    import httpx


@register_backend("myengine")
class MyEngineBackend:
    name: ClassVar[str] = "myengine"

    def __init__(self, *, api_key: str | None = None, language: str = "en") -> None:
        import os
        self._api_key = api_key or os.environ.get("MYENGINE_API_KEY")
        self.language = language

    async def search(
        self,
        query: str,
        *,
        http: httpx.AsyncClient,
        limit: int = 10,
    ) -> list[SearchResult]:
        if not self._api_key:
            raise RuntimeError("MYENGINE_API_KEY is not set")
        resp = await http.get(
            "https://api.myengine.example.com/search",
            params={"q": query, "n": limit, "lang": self.language},
            headers={"Authorization": f"Bearer {self._api_key}"},
            timeout=30.0,
        )
        resp.raise_for_status()
        results = resp.json().get("hits") or []
        return [
            SearchResult(
                url=r["url"],
                title=r["title"],
                snippet=r.get("description", ""),
                raw=r,
            )
            for r in results
            if r.get("url")
        ]
```

Wire it into the registry by adding to `_import_builtins` in
`src/glean/search/registry.py`:

```python
def _import_builtins() -> None:
    from glean.search import brave, exa, myengine, mwmbl, searxng, serper, tavily  # noqa: F401
```

Then YAML can reference it:

```yaml
sources:
  - type: search
    query: "your topic"
    engine: myengine
    api_key: ${MYENGINE_API_KEY}
    language: en
```

## Guidance

- **Use the constructor signature as the YAML API.** Every kwarg in `__init__`
  becomes a valid YAML field. Required positional args become required keys.
- **Use the injected httpx.AsyncClient.** Don't create your own — the runner
  manages connection pooling and timeouts.
- **Always set a `timeout` on requests.** 30 seconds is the convention.
- **Skip results without a URL.** Many search APIs return entries with empty
  `url` for promoted/ad slots; filter them.
- **Set `raw=r`** so downstream pipeline stages (rank, summarize) can access
  engine-specific fields if needed.
- **Surface meaningful errors.** If a misconfiguration is the most likely
  cause of a non-2xx response (like SearXNG's 403 for missing JSON format),
  raise a clear RuntimeError pointing the user at the fix.

## Built-in backends

| Engine | Auth | Free tier | Notes |
|--------|------|-----------|-------|
| `searxng` | None | Unlimited (self-hosted) | Recommended for local-LLM users |
| `brave` | API key | 2k/mo | Best independent index |
| `tavily` | API key | 1k/mo | Returns LLM-friendly synthesized answer |
| `serper` | API key | 2.5k credits | Google-quality SERP |
| `exa` | API key | 1k/mo | Semantic search + full content option |
| `mwmbl` | None | Unlimited | Free open-source community crawler |

See [Web search setup](../getting-started/search.md) for end-user setup
instructions for each backend.
