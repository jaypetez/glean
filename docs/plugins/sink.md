---
title: "Writing a Sink — glean Plugins"
description: Implement and register a custom sink plugin for digest delivery.
---

# Authoring Sinks

A **Sink** is a destination for digest output — Telegram, Discord, a webhook, a
file, or the built-in dashboard history. The sink layer is pluggable, mirroring
the [Source](source.md) and [LLM Provider](llm.md) layers.

## The protocol

```python
# src/glean/sinks/base.py
@runtime_checkable
class Sink(Protocol):
    type: ClassVar[str]
    required: bool

    async def send(self, ctx: SendContext) -> None: ...
    async def aclose(self) -> None: ...
```

`SendContext` carries everything a sink needs:

```python
@dataclass(frozen=True, slots=True)
class SendContext:
    feed: str                   # feed name
    items: list[Item]           # raw items (for rich rendering)
    messages: list[str]         # pre-rendered Telegram-HTML chunks
    intro: str                  # digest header text
    render: RenderConfig        # style, max_items, link_preview
```

A sink can either:

- Use `ctx.messages` directly (already split for Telegram's 4096-char limit)
- Re-render from `ctx.items` for platform-specific formatting (Discord embeds, Slack blocks, JSON payloads)

## Writing a sink

```python
# src/glean/sinks/myservice.py
from __future__ import annotations
from typing import TYPE_CHECKING, ClassVar
import httpx

from glean.logging import get_logger
from glean.sinks.registry import register_sink

if TYPE_CHECKING:
    from glean.sinks.base import SendContext

logger = get_logger(__name__)


@register_sink("myservice")
class MyServiceSink:
    type: ClassVar[str] = "myservice"

    def __init__(
        self,
        api_url: str,
        *,
        token: str | None = None,
        required: bool = True,
    ) -> None:
        if not api_url:
            raise ValueError("myservice sink requires 'api_url'")
        self.api_url = api_url
        self.token = token
        self.required = required
        self._client = httpx.AsyncClient(timeout=30.0)

    async def send(self, ctx: SendContext) -> None:
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        for msg in ctx.messages:
            resp = await self._client.post(
                self.api_url,
                json={"text": msg, "feed": ctx.feed},
                headers=headers,
            )
            resp.raise_for_status()

    async def aclose(self) -> None:
        await self._client.aclose()
```

Wire it into the registry by adding to `_import_builtins` in
`src/glean/sinks/registry.py`:

```python
def _import_builtins() -> None:
    # ... existing imports ...
    from glean.sinks import myservice  # noqa: F401  # add this line
```

Then YAML can reference it:

```yaml
sinks:
  - type: myservice
    api_url: https://example.com/notify
    token: ${MYSERVICE_TOKEN}
    required: false   # optional — failures won't trigger ops alerts
```

## Guidance

- **Use the constructor signature as the YAML API.** Every kwarg in `__init__`
  becomes a valid YAML field. Required positional args become required YAML keys.
- **HTTP clients are per-instance.** Create `httpx.AsyncClient` in `__init__`
  and close it in `aclose()`. Don't share a global client.
- **Handle message splitting yourself.** If your platform has a length limit
  (Discord 2000, Slack 3000, ntfy 4096), split the rendered output before
  sending. The shared `_chunk` helpers in existing sinks are good references.
- **Mark optional sinks with `required=False`.** A failure on a `required=True`
  sink will trigger the ops alert and increment the feed's failure counter.
  Optional sinks just log a warning.
- **Strip Telegram HTML if rendering for non-Telegram platforms.** The
  `ctx.messages` are pre-formatted with Telegram's HTML subset (`<b>`, `<i>`,
  `<a href>`). For other platforms, either re-render from `ctx.items` or use a
  simple regex to strip tags.

## Built-in sinks

| Type | Description |
|------|-------------|
| `dashboard` | Persist rendered digest fragments in SQLite for the built-in web UI and digest APIs. |
| `telegram` | POST to Telegram Bot API. Requires `chat_id` and `TELEGRAM_BOT_TOKEN` env. |
| `discord` | POST to a Discord webhook URL. 2000-char chunks, markdown formatting. |
| `slack` | POST to a Slack incoming webhook. 3000-char chunks, mrkdwn formatting. |
| `ntfy` | POST to ntfy.sh (or self-hosted). Plain-text body with X-Title/X-Priority headers. |
| `webhook` | POST a JSON payload to any URL. Configurable headers and bearer/basic auth. |
| `file` | Append-only writes to a local file. Modes: `text`, `jsonl`, `markdown`. |
