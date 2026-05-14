from __future__ import annotations

from glean.config.schema import RenderConfig
from glean.sources.base import Item
from glean.telegram.render import TELEGRAM_MAX_CHARS, render_digest


def _item(title: str, url: str = "https://example.com/x", body: str = "") -> Item:
    return Item(
        canonical_url=url,
        title=title,
        body=body,
        source_type="rss",
        source_name="example",
        llm_summary="one-line summary",
    )


def test_html_render_single_message() -> None:
    items = [_item(f"item {i}") for i in range(3)]
    msgs = render_digest(items, intro="AI news", render=RenderConfig())
    assert len(msgs) == 1
    assert "AI news" in msgs[0]
    assert "<b>item 0</b>" in msgs[0]
    assert msgs[0].count("📰") == 3


def test_html_escapes_dangerous_chars() -> None:
    items = [_item("<script>alert(1)</script>")]
    msgs = render_digest(items, intro="hi", render=RenderConfig())
    assert "<script>" not in msgs[0]
    assert "&lt;script&gt;" in msgs[0]


def test_html_escapes_intro() -> None:
    items = [_item("safe")]
    msgs = render_digest(items, intro="<script>alert(1)</script>", render=RenderConfig())

    assert "<script>" not in msgs[0]
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in msgs[0]


def test_html_drops_unsafe_link_url() -> None:
    items = [_item("danger", url="javascript:alert(1)")]
    msgs = render_digest(items, intro="hi", render=RenderConfig())

    assert "javascript:alert(1)" not in msgs[0]
    assert "<a href=" not in msgs[0]


def test_markdown_v2_drops_unsafe_link_url() -> None:
    items = [_item("danger", url="javascript:alert(1)")]
    msgs = render_digest(items, intro="hi", render=RenderConfig(style="markdown_v2"))

    assert "javascript:alert(1)" not in msgs[0]
    assert "[link](" not in msgs[0]


def test_markdown_v2_keeps_safe_link_url() -> None:
    items = [_item("safe", url="https://example.com/x")]
    msgs = render_digest(items, intro="hi", render=RenderConfig(style="markdown_v2"))

    assert "[link](https://example.com/x)" in msgs[0]


def test_markdown_v2_escapes_link_url_delimiters() -> None:
    items = [_item("safe", url=r"https://example.com/a)b\c")]
    msgs = render_digest(items, intro="hi", render=RenderConfig(style="markdown_v2"))

    assert r"[link](https://example.com/a\)b\\c)" in msgs[0]


def test_chunking_when_too_long() -> None:
    big_body = "x" * 600
    items = [_item(f"item {i}", body=big_body) for i in range(20)]
    # Force unrealistically long llm_summary to push past Telegram's limit.
    items = [
        Item(
            canonical_url=i.canonical_url,
            title=i.title,
            body=i.body,
            source_type=i.source_type,
            source_name=i.source_name,
            llm_summary="long " * 80,
        )
        for i in items
    ]
    msgs = render_digest(items, intro="hi", render=RenderConfig(max_items=50))
    assert len(msgs) >= 2
    for m in msgs:
        assert len(m) <= TELEGRAM_MAX_CHARS


def test_overflow_footer() -> None:
    items = [_item(f"item {i}") for i in range(3)]
    msgs = render_digest(items, intro="hi", render=RenderConfig(), overflow_count=7)
    assert "7 more" in msgs[-1]


def test_plain_style_strips_html() -> None:
    items = [_item("hello")]
    msgs = render_digest(
        items, intro="<b>AI</b>", render=RenderConfig(style="plain")
    )
    assert "<b>" not in msgs[0]
    assert "AI" in msgs[0]
