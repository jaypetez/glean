"""Slack webhook sink."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, ClassVar

import httpx

from glean.logging import get_logger
from glean.security.ssrf import validate_url
from glean.security.ssrf_transport import SSRFGuardedTransport, outbound_timeout
from glean.sinks.escape import escape_slack, safe_url
from glean.sinks.registry import register_sink

if TYPE_CHECKING:
    from glean.sinks.base import SendContext
    from glean.sources.base import Item

logger = get_logger(__name__)

SLACK_MAX_CHARS = 3000
_TAG_RE = re.compile(r"<[^>]+>")


@register_sink("slack")
class SlackSink:
    """POST messages to a Slack incoming webhook."""

    type: ClassVar[str] = "slack"

    def __init__(
        self,
        webhook_url: str = "",
        *,
        channel: str | None = None,
        username: str | None = None,
        icon_emoji: str | None = None,
        timeout_s: float = 30.0,
        required: bool = True,
    ) -> None:
        if not webhook_url:
            raise ValueError("slack sink requires 'webhook_url'")
        self.webhook_url = validate_url(webhook_url)
        self.channel = channel
        self.username = username
        self.icon_emoji = icon_emoji
        self.required = required
        self._client = httpx.AsyncClient(
            timeout=outbound_timeout(read=timeout_s),
            follow_redirects=False,
            transport=SSRFGuardedTransport(allow_private=False),
        )

    async def send(self, ctx: SendContext) -> None:
        chunks = _render_slack(ctx.items, intro=ctx.intro)
        for chunk in chunks:
            payload: dict[str, Any] = {"text": chunk}
            if self.channel:
                payload["channel"] = self.channel
            if self.username:
                payload["username"] = self.username
            if self.icon_emoji:
                payload["icon_emoji"] = self.icon_emoji
            resp = await self._client.post(self.webhook_url, json=payload)
            resp.raise_for_status()
        logger.debug("slack_sent", feed=ctx.feed, chunks=len(chunks))

    async def aclose(self) -> None:
        await self._client.aclose()


def _render_slack(items: list[Item], *, intro: str) -> list[str]:
    """Render items as Slack mrkdwn, splitting at SLACK_MAX_CHARS."""
    blocks: list[str] = []
    if intro:
        clean = _strip_html(intro)
        if clean:
            blocks.append(f"*{clean}*")

    for item in items:
        title = escape_slack(item.title or "(untitled)")
        summary = escape_slack(_strip_html(item.llm_summary or item.summary or ""))
        url = _escape_slack_link_url(safe_url(item.canonical_url))
        source = item.source_name or item.source_type or ""

        if url:
            lines = [f"*<{url}|{title}>*"]
        else:
            lines = [f"*{title}*"]
        if summary:
            lines.append(summary)
        if source:
            lines.append(f"_{source}_")
        blocks.append("\n".join(lines))

    return _chunk(blocks, SLACK_MAX_CHARS)


def _strip_html(text: str) -> str:
    return _TAG_RE.sub("", text).strip()


def _escape_slack_link_url(url: str) -> str:
    return (
        url.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("|", "%7C")
    )


def _chunk(blocks: list[str], max_chars: int) -> list[str]:
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
