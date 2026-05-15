from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from glean.config.schema import RenderConfig
from glean.sources.base import Item
from glean.telegram.render import TELEGRAM_MAX_CHARS, _html_escape, render_digest

_TEXT = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",)),
    min_size=0,
)


def _bounded_text(max_size: int) -> st.SearchStrategy[str]:
    return _TEXT.filter(lambda s: len(s) <= max_size)


_URL = st.one_of(
    st.just(""),
    _bounded_text(80).map(lambda path: f"https://example.com/{path}"),
)

_ITEM = st.builds(
    Item,
    canonical_url=_URL,
    title=_bounded_text(120),
    body=_bounded_text(500),
    summary=st.one_of(st.none(), _bounded_text(600)),
    source_type=st.sampled_from(["rss", "hn", "reddit", "scraper", "search", "custom"]),
    source_name=_bounded_text(50),
    llm_summary=st.one_of(st.none(), _bounded_text(600)),
)


@given(
    items=st.lists(_ITEM, max_size=12),
    intro=_bounded_text(200),
    style=st.sampled_from(["html", "markdown_v2", "plain"]),
    overflow_count=st.integers(min_value=0, max_value=1_000),
)
@settings(max_examples=100, deadline=1000)
def test_render_digest_chunks_fit_telegram_limit(
    items: list[Item],
    intro: str,
    style: str,
    overflow_count: int,
) -> None:
    chunks = render_digest(
        items,
        intro=intro,
        render=RenderConfig(style=style, max_items=50),
        overflow_count=overflow_count,
    )

    assert all(len(chunk) <= TELEGRAM_MAX_CHARS for chunk in chunks)


@given(_bounded_text(300))
@settings(max_examples=100, deadline=1000)
def test_html_escape_is_idempotent(s: str) -> None:
    escaped = _html_escape(s)

    assert _html_escape(escaped) == escaped
