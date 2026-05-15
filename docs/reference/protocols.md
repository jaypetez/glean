---
title: Plugin Protocols — glean
description: Runtime contracts for Source, Sink, LLMProvider, and SearchBackend plugins.
---

# Plugin Protocols

This reference is for plugin authors who need the exact runtime contracts. The code blocks copy the current protocol classes from `src/glean`, followed by method contracts and concurrency notes.

## Source

Source: `src/glean/sources/base.py`

```python
@runtime_checkable
class Source(Protocol):
    type: ClassVar[str]

    async def fetch(self, ctx: FetchContext) -> list[Item]:
        pass
```

!!! note "Contract"
    **`fetch(ctx)`** receives a `FetchContext` with `feed_name`, an injected `httpx.AsyncClient`, the open `StateStore`, and optional `since` timestamp. Return a list of normalized `Item` objects; return an empty list when the upstream has no new content.

    You may raise exceptions for invalid configuration, HTTP failures, parse failures, or state errors. `Runner._fetch_all()` catches source exceptions, logs `source_failed`, and continues the feed with items from other sources.

    Sources are fetched sequentially within a feed run today. Multiple feed runs can still overlap in the daemon, so avoid process-wide mutable state unless it is protected.

## Sink

Source: `src/glean/sinks/base.py`

```python
@runtime_checkable
class Sink(Protocol):
    """A destination for digest output."""

    type: ClassVar[str]
    required: bool

    async def send(self, ctx: SendContext) -> None:
        pass

    async def aclose(self) -> None:
        pass
```

!!! note "Contract"
    **`send(ctx)`** receives `SendContext` with the feed name, final `Item` list, rendered message chunks, intro text, and render settings. Return `None` after the destination accepts every required payload.

    Raise for destination failures that should count as a failed sink delivery. Required sink failures become feed failures; optional sink failures are logged and do not fail the feed.

    All configured sinks for a feed are called concurrently with `asyncio.gather()`. `aclose()` is called during runner shutdown and should close clients without raising on repeated calls.

## LLMProvider

Source: `src/glean/llm/base.py`

```python
@runtime_checkable
class LLMProvider(Protocol):
    name: ClassVar[str]
    model: str

    async def rank(self, item: Item, prompt: str) -> float:
        """Return relevance in [0, 1]."""

    async def summarize(self, item: Item, prompt: str) -> str:
        """Return a plain-text summary; renderer adds markup."""

    async def digest(self, items: list[Item], prompt: str) -> str:
        """Optional: synthesize a header/intro line for the digest."""

    async def extract(
        self,
        item: Item,
        prompt: str,
        output_schema: dict[str, Any],
        *,
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        """Extract structured data matching output_schema (JSON Schema dict).

        Returns {} on parse/extraction failure.
        """

    async def aclose(self) -> None:
        pass
```

!!! note "Contract"
    **`rank(item, prompt)`** receives one `Item` and the configured rank prompt. Return a float from `0.0` to `1.0`; the rank stage drops items below `min_relevance`.

    **`summarize(item, prompt)`** receives one `Item` and returns plain text. The renderer adds Telegram HTML, Markdown, or plain formatting later.

    **`digest(items, prompt)`** receives the final item list for the feed run and returns an intro/header string. If it raises, glean falls back to the configured intro text.

    **`extract(item, prompt, output_schema, system_prompt=None)`** receives one `Item`, a rendered skill prompt, and a JSON Schema dict. Return a dict matching the schema; return `{}` when extraction fails to parse.

    `rank`, `summarize`, and `extract` are called concurrently from up to 4 workers per pipeline stage. `digest` runs once per digest stage, and `aclose()` runs during shutdown.

## SearchBackend

Source: `src/glean/search/base.py`

```python
@runtime_checkable
class SearchBackend(Protocol):
    """Protocol every search backend must satisfy."""

    name: ClassVar[str]

    async def search(
        self,
        query: str,
        *,
        http: httpx.AsyncClient,
        limit: int = 10,
    ) -> list[SearchResult]:
        pass
```

!!! note "Contract"
    **`search(query, *, http, limit)`** receives the user query, an injected `httpx.AsyncClient`, and the maximum result count. Return normalized `SearchResult` objects and filter entries without URLs.

    Raise for missing credentials, non-retryable upstream errors, or malformed responses that should fail the search source. The search source lets those exceptions bubble to source handling, where the runner logs `source_failed`.

    A backend is called once per search source fetch. Use the injected client rather than creating your own so the runner controls pooling, timeouts, and SSRF protections.
