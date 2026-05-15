---
title: "Writing an LLM Provider — glean Plugins"
description: Implement and register a custom LLM provider for ranking, summarization, and extraction.
---

# Writing an LLM Provider

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

## Guidance

- **`rank` must return `[0, 1]`.** `parse_score` is lenient — accepts `"0.7"`, `"70%"`, `"high"`. Use it.
- **`summarize` returns plain text.** The renderer applies HTML/Markdown.
- **Don't reuse a global client across providers.** Each `__init__` builds its own; the runner caches the *instance* per (provider, model, base_url) tuple.
- **Implement `aclose`.** The daemon calls it on shutdown.
