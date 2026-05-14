from __future__ import annotations

import pytest

from glean.security.scrub import scrub


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", ""),
        ("plain text with no secrets", "plain text with no secrets"),
        ("key sk-abc12345 here", "key sk-[REDACTED] here"),
        ("prefix sk-ABC_123-xyz suffix", "prefix sk-[REDACTED] suffix"),
        ("Authorization: Bearer abcdefghij", "Authorization: Bearer [REDACTED]"),
        (
            "Bearer abc.def_ghi-jkl",
            "Bearer [REDACTED]",
        ),
        ("callback?token=abcdefghij", "callback?token=[REDACTED]"),
        ("callback?TOKEN=abc.def_ghi-jkl", "callback?TOKEN=[REDACTED]"),
        ("api_key=abcdefghij", "api_key=[REDACTED]"),
        ("api-key: abcdefghij", "api-key: [REDACTED]"),
        ('apiKey: "abc.def_ghi-jkl"', 'apiKey: "[REDACTED]"'),
        ('api_key": "abcdefghij"', 'api_key": "[REDACTED]"'),
        (
            "https://api.telegram.org/bot12345678:ABC_def/sendMessage",
            "https://api.telegram.org/bot[REDACTED]/sendMessage",
        ),
        (
            "POST /bot12345678:ABC_def/sendMessage api_key=abcdefghij token=zyxwvutsrq",
            "POST /bot[REDACTED]/sendMessage api_key=[REDACTED] token=[REDACTED]",
        ),
    ],
)
def test_scrub_redacts_secret_patterns(text: str, expected: str) -> None:
    assert scrub(text) == expected
