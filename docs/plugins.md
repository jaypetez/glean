# Authoring plugins

Two extension points: **Source** and **LLMProvider**. Both are tiny protocols; you implement them and decorate with a registry call.

## Writing a Source

A Source produces `Item`s for a single feed tick.

```python
# src/glean/sources/mysource.py
from __future__ import annotations
from typing import ClassVar
from glean.sources.base import FetchContext, Item
from glean.sources.registry import register_source

@register_source("mysource")
class MySource:
    type: ClassVar[str] = "mysource"

    def __init__(self, *, foo: str, limit: int = 20) -> None:
        self.foo = foo
        self.limit = limit

    async def fetch(self, ctx: FetchContext) -> list[Item]:
        resp = await ctx.http.get(f"https://example.com/api?q={self.foo}")
        resp.raise_for_status()
        return [
            Item(
                canonical_url=row["url"],
                title=row["title"],
                body=row.get("body", ""),
                source_type="mysource",
                source_name=f"mysource:{self.foo}",
            )
            for row in resp.json()[: self.limit]
        ]
```

Wire it into the registry by importing in `sources/registry.py::_import_builtins`. Then YAML can reference it:

```yaml
sources:
  - type: mysource
    foo: kittens
    limit: 5
```

### Guidance

- **Honor `ctx.state` for ETag/Last-Modified** when fetching anything cacheable. See `rss.py` for the pattern.
- **Set `canonical_url`** to something stable per item — that's the dedup key. If the source has no URL, leave it empty and dedup will hash `title + body`.
- **Be tolerant of partial failures.** A bad row shouldn't kill the whole fetch.
- **Don't sleep.** The runner has its own concurrency budget; just `await ctx.http.get(...)` and return.

## Writing an LLMProvider

```python
# src/glean/llm/myllm.py
from __future__ import annotations
from typing import ClassVar
from glean.llm.registry import register_provider
from glean.llm.common import parse_score, item_as_prompt_context, items_as_prompt_context
from glean.sources.base import Item

@register_provider("myllm")
class MyLLMProvider:
    name: ClassVar[str] = "myllm"

    def __init__(self, *, model: str, api_key: str | None = None, **_: object) -> None:
        self.model = model
        # ...client setup...

    async def rank(self, item: Item, prompt: str) -> float:
        out = await self._complete(prompt, item_as_prompt_context(item), max_tokens=16)
        return parse_score(out)

    async def summarize(self, item: Item, prompt: str) -> str:
        return await self._complete(prompt, item_as_prompt_context(item), max_tokens=256)

    async def digest(self, items: list[Item], prompt: str) -> str:
        return await self._complete(prompt, items_as_prompt_context(items), max_tokens=256)

    async def aclose(self) -> None: ...
```

Then in YAML:

```yaml
llm:
  provider: myllm
  model: my-fast-model
```

### Guidance

- **`rank` must return `[0, 1]`.** `parse_score` is lenient — accepts `"0.7"`, `"70%"`, `"high"`. Use it.
- **`summarize` returns plain text.** The renderer applies HTML/Markdown.
- **Don't reuse a global client across providers.** Each `__init__` builds its own; the runner caches the *instance* per (provider, model, base_url) tuple.
- **Implement `aclose`.** The daemon calls it on shutdown.
