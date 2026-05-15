---
title: "Writing a Source — glean Plugins"
description: Implement and register a custom source plugin for glean.
---

# Writing a Source

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

## Guidance

- **Honor `ctx.state` for ETag/Last-Modified** when fetching anything cacheable. See `rss.py` for the pattern.
- **Set `canonical_url`** to something stable per item — that's the dedup key. If the source has no URL, leave it empty and dedup will hash `title + body`.
- **Be tolerant of partial failures.** A bad row shouldn't kill the whole fetch.
- **Don't sleep.** The runner has its own concurrency budget; just `await ctx.http.get(...)` and return.
