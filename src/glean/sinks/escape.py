"""Per-platform escape helpers + safe URL filter."""

from __future__ import annotations

import re
from urllib.parse import urlparse

_DISCORD_SPECIAL = re.compile(r"([*_~`\\|<>\[\]\(\)@])")
_SLACK_SPECIAL = re.compile(r"([*_~`])")
_SAFE_SCHEMES = {"http", "https"}


def escape_discord(text: str | None) -> str:
    return _DISCORD_SPECIAL.sub(r"\\\1", text or "")


def escape_slack(text: str | None) -> str:
    text = (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return _SLACK_SPECIAL.sub(r"\\\1", text)


def safe_url(url: str | None) -> str:
    if not url or any(char.isspace() for char in url):
        return ""
    try:
        scheme = urlparse(url).scheme.lower()
    except Exception:
        return ""
    return url if scheme in _SAFE_SCHEMES else ""
