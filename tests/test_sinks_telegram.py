"""TelegramSink wrapper and configuration tests."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


@pytest.fixture
def patched_telegram_sender(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    """Replace TelegramSender inside sinks.telegram with a stub."""
    from glean.sinks import telegram as sink_module

    sent: list[dict[str, object]] = []

    class StubSender:
        def __init__(self, token: str, *, base_url: str | None = None) -> None:
            self.token = token
            self.base_url = base_url

        async def send_digest(
            self,
            chat_id: int | str,
            messages: list[str],
            *,
            style: str = "html",
            link_preview: bool = False,
        ) -> None:
            sent.append(
                {
                    "chat_id": chat_id,
                    "messages": list(messages),
                    "style": style,
                    "link_preview": link_preview,
                    "token": self.token,
                }
            )

        async def aclose(self) -> None:
            pass

    monkeypatch.setattr(sink_module, "TelegramSender", StubSender)
    return sent


async def test_telegram_sink_requires_token(monkeypatch: pytest.MonkeyPatch) -> None:
    from glean.sinks.registry import build_sink

    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    with pytest.raises(ValueError, match="token"):
        build_sink({"type": "telegram", "chat_id": 12345})


async def test_telegram_sink_uses_explicit_token(
    patched_telegram_sender: list[dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from glean.config.schema import RenderConfig
    from glean.sinks.base import SendContext
    from glean.sinks.registry import build_sink

    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    sink = build_sink({"type": "telegram", "chat_id": 99, "token": "explicit-token"})
    ctx = SendContext(feed="t", items=[], messages=["hello"], intro="", render=RenderConfig())

    await sink.send(ctx)
    await sink.aclose()

    assert len(patched_telegram_sender) == 1
    assert patched_telegram_sender[0]["chat_id"] == 99
    assert patched_telegram_sender[0]["token"] == "explicit-token"


async def test_telegram_sink_uses_env_token(
    patched_telegram_sender: list[dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from glean.config.schema import RenderConfig
    from glean.sinks.base import SendContext
    from glean.sinks.registry import build_sink

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "env-token")
    sink = build_sink({"type": "telegram", "chat_id": 42})
    ctx = SendContext(feed="t", items=[], messages=["m"], intro="", render=RenderConfig())

    await sink.send(ctx)
    await sink.aclose()

    assert patched_telegram_sender[0]["chat_id"] == 42
    assert patched_telegram_sender[0]["token"] == "env-token"


async def test_telegram_sink_default_required(
    patched_telegram_sender: list[dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from glean.sinks.registry import build_sink

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    # The fixture patches TelegramSender so build_sink never constructs a real Bot.

    sink = build_sink({"type": "telegram", "chat_id": 1})

    assert sink.required is True


async def test_telegram_sink_optional(
    patched_telegram_sender: list[dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from glean.sinks.registry import build_sink

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    # The fixture patches TelegramSender so build_sink never constructs a real Bot.

    sink = build_sink({"type": "telegram", "chat_id": 1, "required": False})

    assert sink.required is False


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
