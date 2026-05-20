from __future__ import annotations

import html
import re
from typing import TYPE_CHECKING

from glean.sinks.escape import safe_url

if TYPE_CHECKING:
    from glean.sinks.base import SendContext
    from glean.sources.base import Item

_TAG_RE = re.compile(r"<[^>]+>")
_SYSTEM_FONT_STACK = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"


def render_email_html(ctx: SendContext) -> str:
    """Render the digest as inline-styled HTML safe for Gmail/Outlook/Apple Mail."""
    intro = _plaintext(ctx.intro)
    parts = [
        "<html><body style=\"margin:0;padding:0;background-color:#f8fafc;\">",
        (
            "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" "
            "style=\"background-color:#f8fafc;padding:24px 0;\"><tr><td align=\"center\">"
        ),
        (
            "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" "
            "style=\"max-width:680px;width:100%;background-color:#ffffff;border:1px solid #e2e8f0;"
            f"border-radius:12px;font-family:{_SYSTEM_FONT_STACK};\">"
        ),
        (
            "<tr><td "
            "style=\"padding:24px 24px 12px 24px;font-size:24px;line-height:32px;color:#0f172a;\">"
            "<span style=\"color:#0369a1;font-weight:bold\">glean</span>"
            "</td></tr>"
        ),
    ]
    if intro:
        parts.append(
            "<tr><td style=\"padding:0 24px 8px 24px;\">"
            f"<h2 style=\"margin:0;font-size:22px;line-height:30px;"
            f"color:#0f172a;\">{html.escape(intro)}</h2>"
            "</td></tr>"
        )
    if ctx.items:
        for item in ctx.items:
            parts.append(_render_item_row(item))
    else:
        parts.append(
            "<tr><td "
            "style=\"padding:8px 24px 24px 24px;font-size:16px;line-height:24px;color:#475569;\">"
            "No new items matched your criteria this run."
            "</td></tr>"
        )
    parts.append(
        "<tr><td style=\"padding:16px 24px 24px 24px;font-size:13px;line-height:20px;color:#64748b;"
        "border-top:1px solid #e2e8f0;\">Powered by glean</td></tr>"
    )
    parts.append("</table></td></tr></table></body></html>")
    return "".join(parts)


def render_email_plaintext(ctx: SendContext) -> str:
    """Render a plain-text fallback."""
    lines: list[str] = []
    intro = _plaintext(ctx.intro)
    if intro:
        lines.append(intro)
        lines.append("")
    if not ctx.items:
        lines.append("No new items matched your criteria this run.")
        lines.append("")
        lines.append("Powered by glean")
        return "\n".join(lines)
    for item in ctx.items:
        lines.append(_plaintext(item.title) or "(untitled)")
        summary = _plaintext(item.llm_summary or item.summary or "")
        if summary:
            lines.append(f"  {summary}")
        url = safe_url(item.canonical_url)
        if url:
            lines.append(f"  {url}")
        source = _plaintext(item.source_name or item.source_type)
        if source:
            lines.append(f"  Source: {source}")
        lines.append("")
    lines.append("Powered by glean")
    return "\n".join(lines)


def _render_item_row(item: Item) -> str:
    title = html.escape(item.title or "(untitled)")
    summary = html.escape(item.llm_summary or item.summary or "")
    source = html.escape(item.source_name or item.source_type)
    url = html.escape(safe_url(item.canonical_url), quote=True)

    title_html = title
    if url:
        title_html = (
            f"<a href=\"{url}\" "
            f"style=\"color:#0369a1;text-decoration:none;font-weight:600;\">{title}</a>"
        )
    summary_html = ""
    if summary:
        summary_html = (
            f"<div style=\"margin-top:8px;font-size:15px;line-height:22px;"
            f"color:#334155;\">{summary}</div>"
        )
    source_html = ""
    if source:
        source_html = (
            f"<div style=\"margin-top:8px;font-size:13px;line-height:20px;"
            f"color:#64748b;\">{source}</div>"
        )
    return (
        "<tr><td style=\"padding:12px 24px;border-top:1px solid #e2e8f0;\">"
        f"<div style=\"font-size:17px;line-height:24px;color:#0f172a;\">{title_html}</div>"
        f"{summary_html}{source_html}"
        "</td></tr>"
    )


def _plaintext(value: str | None) -> str:
    stripped = _TAG_RE.sub("", value or "")
    return html.unescape(stripped).strip()
