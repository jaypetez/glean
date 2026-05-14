from __future__ import annotations

import re

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"sk-[A-Za-z0-9_-]{8,}"), "sk-[REDACTED]"),
    (re.compile(r"(Bearer\s+)([A-Za-z0-9_.\-]{10,})"), r"\1[REDACTED]"),
    (re.compile(r"(token=)([A-Za-z0-9_.\-]{10,})", re.IGNORECASE), r"\1[REDACTED]"),
    (
        re.compile(
            r"(api[_-]?key[\"\']?\s*[:=]\s*[\"\']?)([A-Za-z0-9_.\-]{10,})",
            re.IGNORECASE,
        ),
        r"\1[REDACTED]",
    ),
    (re.compile(r"(/bot)([0-9]{8,}:[A-Za-z0-9_-]+)"), r"\1[REDACTED]"),
]


def scrub(text: str) -> str:
    for pat, repl in _PATTERNS:
        text = pat.sub(repl, text)
    return text
