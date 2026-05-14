from __future__ import annotations

import re
from html import escape

from glean.config.schema import RenderConfig
from glean.sinks.escape import safe_url
from glean.sources.base import Item

_TAG_RE = re.compile(r"<[^>]+>")

TELEGRAM_MAX_CHARS = 4096

SOURCE_EMOJI: dict[str, str] = {
    "rss": "📰",
    "hn": "🟠",
    "reddit": "👽",
    "scraper": "🔍",
    "search": "🌐",
}


def render_digest(
    items: list[Item],
    *,
    intro: str,
    render: RenderConfig,
    overflow_count: int = 0,
) -> list[str]:
    """Render a digest into one or more Telegram-sized message chunks."""
    if render.style == "plain":
        formatter = _format_item_plain
        intro_line = _strip_tags(intro)
    elif render.style == "markdown_v2":
        formatter = _format_item_markdown
        intro_line = intro
    else:
        formatter = _format_item_html
        intro_line = escape(intro)

    blocks: list[str] = [intro_line] if intro_line else []
    for item in items:
        blocks.append(formatter(item))

    if overflow_count > 0:
        blocks.append(_overflow_line(overflow_count, render.style))

    return _chunk(blocks, render.style)


def _format_item_html(item: Item) -> str:
    emoji = SOURCE_EMOJI.get(item.source_type, "•")
    title = escape(item.title or "(untitled)")
    summary = escape(item.llm_summary or item.summary or "")
    source_name = escape(item.source_name or item.source_type or "")
    url = escape(safe_url(item.canonical_url))

    lines = [f"<b>{title}</b>"]
    if summary:
        lines.append(summary)
    footer = f"<i>{emoji} {source_name}</i>"
    if url:
        footer += f' · <a href="{url}">link</a>'
    lines.append(footer)
    return "\n".join(lines)


def _format_item_markdown(item: Item) -> str:
    emoji = SOURCE_EMOJI.get(item.source_type, "•")
    title = _md_escape(item.title or "(untitled)")
    summary = _md_escape(item.llm_summary or item.summary or "")
    source_name = _md_escape(item.source_name or item.source_type or "")
    url = _md_link_url_escape(safe_url(item.canonical_url))

    lines = [f"*{title}*"]
    if summary:
        lines.append(summary)
    footer = f"_{emoji} {source_name}_"
    if url:
        footer += f" · [link]({url})"
    lines.append(footer)
    return "\n".join(lines)


def _md_link_url_escape(url: str) -> str:
    return url.replace("\\", "\\\\").replace(")", r"\)")


def _format_item_plain(item: Item) -> str:
    emoji = SOURCE_EMOJI.get(item.source_type, "•")
    parts = [item.title or "(untitled)"]
    if summary := (item.llm_summary or item.summary):
        parts.append(summary)
    footer = f"{emoji} {item.source_name or item.source_type or ''}"
    if item.canonical_url:
        footer += f" — {item.canonical_url}"
    parts.append(footer)
    return "\n".join(parts)


def _overflow_line(n: int, style: str) -> str:
    text = f"…and {n} more (lowest-ranked items hidden)."
    if style == "html":
        return f"<i>{escape(text)}</i>"
    if style == "markdown_v2":
        return f"_{_md_escape(text)}_"
    return text


def _strip_tags(s: str) -> str:
    return _TAG_RE.sub("", s).strip()


_MD_SPECIAL = r"_*[]()~`>#+-=|{}.!\\"


def _md_escape(s: str) -> str:
    return "".join("\\" + c if c in _MD_SPECIAL else c for c in s)


def _chunk(blocks: list[str], style: str) -> list[str]:
    """Glue blocks with blank lines, splitting at TELEGRAM_MAX_CHARS."""
    if not blocks:
        return []
    sep = "\n\n"
    messages: list[str] = []
    current: list[str] = []
    current_len = 0

    for block in blocks:
        block_len = len(block) + (len(sep) if current else 0)
        if current_len + block_len > TELEGRAM_MAX_CHARS - 32 and current:
            messages.append(sep.join(current))
            current = [block]
            current_len = len(block)
        else:
            current.append(block)
            current_len += block_len

    if current:
        messages.append(sep.join(current))

    if len(messages) > 1:
        total = len(messages)
        messages = [f"({i + 1}/{total}) {m}" for i, m in enumerate(messages)]

    return messages
