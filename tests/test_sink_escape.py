from __future__ import annotations

import pytest

from glean.sinks.escape import escape_discord, escape_slack, safe_url


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", ""),
        ("*bold*", r"\*bold\*"),
        ("[click](evil)", r"\[click\]\(evil\)"),
        ("@everyone", r"\@everyone"),
        ("_tilde~ `code` | <tag>", r"\_tilde\~ \`code\` \| \<tag\>"),
    ],
)
def test_escape_discord_escapes_markdown_control_chars(text: str, expected: str) -> None:
    assert escape_discord(text) == expected


def test_escape_discord_handles_none_like_empty_string() -> None:
    assert escape_discord(None) == ""


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("<script>", "&lt;script&gt;"),
        ("*bold*", r"\*bold\*"),
        ("_tilde~ `code`", r"\_tilde\~ \`code\`"),
        ("a & b", "a &amp; b"),
    ],
)
def test_escape_slack_escapes_entities_and_formatting(text: str, expected: str) -> None:
    assert escape_slack(text) == expected


def test_escape_slack_handles_none_like_empty_string() -> None:
    assert escape_slack(None) == ""


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("javascript:alert(1)", ""),
        ("data:text/html,<script>alert(1)</script>", ""),
        ("file:///etc/passwd", ""),
        ("https://example.com/evil\nnext", ""),
        ("https://example.com", "https://example.com"),
        (None, ""),
        ("", ""),
    ],
)
def test_safe_url_allows_only_http_and_https(url: str | None, expected: str) -> None:
    assert safe_url(url) == expected
