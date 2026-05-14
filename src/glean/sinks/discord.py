"""Discord webhook sink."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, ClassVar

import httpx

from glean.logging import get_logger
from glean.security.ssrf import validate_url
from glean.security.ssrf_transport import SSRFGuardedTransport, outbound_timeout
from glean.sinks.registry import register_sink

if TYPE_CHECKING:
    from glean.sinks.base import SendContext
    from glean.sources.base import Item

logger = get_logger(__name__)

DISCORD_MAX_CHARS = 2000
_TAG_RE = re.compile(r"<[^>]+>")


@register_sink("discord")
class DiscordSink:
    """POST messages to a Discord webhook."""

    type: ClassVar[str] = "discord"

    def __init__(
        self,
        webhook_url: str = "",
        *,
        username: str | None = None,
        avatar_url: str | None = None,
        timeout_s: float = 30.0,
        required: bool = True,
    ) -> None:
        if not webhook_url:
            raise ValueError("discord sink requires 'webhook_url'")
        self.webhook_url = validate_url(webhook_url)
        self.username = username
        self.avatar_url = avatar_url
        self.required = required
        self._client = httpx.AsyncClient(
            timeout=outbound_timeout(read=timeout_s),
            follow_redirects=False,
            transport=SSRFGuardedTransport(allow_private=False),
        )

    async def send(self, ctx: SendContext) -> None:
        chunks = _render_discord(ctx.items, intro=ctx.intro)
        for chunk in chunks:
            payload: dict[str, Any] = {"content": chunk}
            if self.username:
                payload["username"] = self.username
            if self.avatar_url:
                payload["avatar_url"] = self.avatar_url
            resp = await self._client.post(self.webhook_url, json=payload)
            resp.raise_for_status()
        logger.debug("discord_sent", feed=ctx.feed, chunks=len(chunks))

    async def aclose(self) -> None:
        await self._client.aclose()


def _render_discord(items: list[Item], *, intro: str) -> list[str]:
    """Render items as Discord markdown, splitting at 2000 chars."""
    blocks: list[str] = []
    if intro:
        clean_intro = _strip_html(intro)
        if clean_intro:
            blocks.append(f"**{clean_intro}**")

    for item in items:
        title = item.title or "(untitled)"
        summary = item.llm_summary or item.summary or ""
        url = item.canonical_url or ""
        source = item.source_name or item.source_type or ""

        lines = [f"**{title}**"]
        if summary:
            lines.append(_strip_html(summary))
        footer_parts = []
        if source:
            footer_parts.append(f"_{source}_")
        if url:
            footer_parts.append(f"<{url}>")
        if footer_parts:
            lines.append(" · ".join(footer_parts))
        blocks.append("\n".join(lines))

    return _chunk(blocks, DISCORD_MAX_CHARS)


def _strip_html(text: str) -> str:
    return _TAG_RE.sub("", text).strip()


def _chunk(blocks: list[str], max_chars: int) -> list[str]:
    """Glue blocks with blank lines, splitting at max_chars."""
    if not blocks:
        return []
    sep = "\n\n"
    messages: list[str] = []
    current: list[str] = []
    current_len = 0

    for block in blocks:
        if len(block) > max_chars:
            if current:
                messages.append(sep.join(current))
                current = []
                current_len = 0
            messages.extend(_split_block(block, max_chars))
            continue

        block_len = len(block) + (len(sep) if current else 0)
        if current_len + block_len > max_chars and current:
            messages.append(sep.join(current))
            current = [block]
            current_len = len(block)
        else:
            current.append(block)
            current_len += block_len

    if current:
        messages.append(sep.join(current))

    return messages


def _split_block(block: str, max_chars: int) -> list[str]:
    return [block[i : i + max_chars] for i in range(0, len(block), max_chars)]
