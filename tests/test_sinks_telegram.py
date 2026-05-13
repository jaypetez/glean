"""Telegram sink configuration tests."""
from __future__ import annotations

import pytest


def test_telegram_sink_accepts_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """The base_url param should be propagated to the underlying Bot."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    captured: dict[str, object] = {}

    class StubBot:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    from glean.telegram import client as tc

    monkeypatch.setattr(tc, "Bot", StubBot)

    from glean.sinks.registry import build_sink

    build_sink(
        {
            "type": "telegram",
            "chat_id": 12345,
            "base_url": "http://mock-telegram:8001",
        }
    )

    assert captured["base_url"] == "http://mock-telegram:8001/bot"
    assert captured["base_file_url"] == "http://mock-telegram:8001/file/bot"


def test_telegram_sink_reads_env_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """If no explicit base_url, fall back to TELEGRAM_BASE_URL env var."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("TELEGRAM_BASE_URL", "http://localhost:8001/")
    captured: dict[str, object] = {}

    class StubBot:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    from glean.telegram import client as tc

    monkeypatch.setattr(tc, "Bot", StubBot)

    from glean.sinks.registry import build_sink

    build_sink({"type": "telegram", "chat_id": 12345})

    assert captured["base_url"] == "http://localhost:8001/bot"
    assert captured["base_file_url"] == "http://localhost:8001/file/bot"


def test_telegram_sink_no_base_url_uses_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without base_url, Bot is constructed without it (uses Telegram default)."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.delenv("TELEGRAM_BASE_URL", raising=False)
    captured: dict[str, object] = {}

    class StubBot:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    from glean.telegram import client as tc

    monkeypatch.setattr(tc, "Bot", StubBot)

    from glean.sinks.registry import build_sink

    build_sink({"type": "telegram", "chat_id": 12345})

    assert "base_url" not in captured
    assert "base_file_url" not in captured
