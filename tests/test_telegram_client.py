"""TelegramSender retry and backoff tests."""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from telegram.error import RetryAfter, TimedOut

from glean.telegram.client import TelegramSender

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_bot(monkeypatch: pytest.MonkeyPatch) -> tuple[AsyncMock, AsyncMock]:
    """Patch python-telegram-bot's Bot class with a mock."""
    from glean.telegram import client as tc

    mock_send = AsyncMock(return_value=None)
    mock_shutdown = AsyncMock(return_value=None)

    class FakeBot:
        send_message = mock_send
        shutdown = mock_shutdown

        def __init__(self, token: str) -> None:
            self.token = token

    monkeypatch.setattr(tc, "Bot", FakeBot)
    return mock_send, mock_shutdown


async def test_send_digest_sends_each_message(
    mock_bot: tuple[AsyncMock, AsyncMock],
) -> None:
    send_mock, _ = mock_bot
    sender = TelegramSender("test-token")

    await sender.send_digest(
        chat_id=12345,
        messages=["msg1", "msg2", "msg3"],
        style="html",
        link_preview=False,
    )

    assert send_mock.await_count == 3


async def test_send_digest_with_plain_style_sets_no_parse_mode(
    mock_bot: tuple[AsyncMock, AsyncMock],
) -> None:
    send_mock, _ = mock_bot
    sender = TelegramSender("test-token")

    await sender.send_digest(chat_id=1, messages=["text"], style="plain")

    call = send_mock.await_args
    assert call.kwargs.get("parse_mode") is None


async def test_send_digest_link_preview_disabled_by_default(
    mock_bot: tuple[AsyncMock, AsyncMock],
) -> None:
    send_mock, _ = mock_bot
    sender = TelegramSender("test-token")

    await sender.send_digest(chat_id=1, messages=["text"])

    opts = send_mock.await_args.kwargs.get("link_preview_options")
    assert opts is not None
    assert opts.is_disabled is True


async def test_send_with_retry_handles_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    from glean.telegram import client as tc

    call_count = {"n": 0}
    sleep_mock = AsyncMock(return_value=None)
    monkeypatch.setenv("PTB_TIMEDELTA", "1")
    monkeypatch.setattr(tc.asyncio, "sleep", sleep_mock)

    async def flaky_send(*args: object, **kwargs: object) -> None:
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RetryAfter(retry_after=timedelta(seconds=0.01))

    class FakeBot:
        send_message = staticmethod(flaky_send)
        shutdown = AsyncMock()

        def __init__(self, token: str) -> None:
            self.token = token

    monkeypatch.setattr(tc, "Bot", FakeBot)

    sender = TelegramSender("test-token")
    await sender.send_text(chat_id=1, text="hello")

    assert call_count["n"] == 2
    sleep_mock.assert_awaited_once_with(0.51)


async def test_send_with_retry_handles_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    from glean.telegram import client as tc

    call_count = {"n": 0}
    sleep_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(tc.asyncio, "sleep", sleep_mock)

    async def flaky_send(*args: object, **kwargs: object) -> None:
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise TimedOut

    class FakeBot:
        send_message = staticmethod(flaky_send)
        shutdown = AsyncMock()

        def __init__(self, token: str) -> None:
            self.token = token

    monkeypatch.setattr(tc, "Bot", FakeBot)

    sender = TelegramSender("test-token")
    await sender.send_text(chat_id=1, text="hello")

    assert call_count["n"] == 3
    assert [call.args[0] for call in sleep_mock.await_args_list] == [1.0, 2.0]


async def test_send_with_retry_gives_up_after_max_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from glean.telegram import client as tc

    sleep_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(tc.asyncio, "sleep", sleep_mock)

    async def always_timeout(*args: object, **kwargs: object) -> None:
        raise TimedOut

    class FakeBot:
        send_message = staticmethod(always_timeout)
        shutdown = AsyncMock()

        def __init__(self, token: str) -> None:
            self.token = token

    monkeypatch.setattr(tc, "Bot", FakeBot)

    sender = TelegramSender("test-token")
    with pytest.raises(TimedOut):
        await sender.send_text(chat_id=1, text="hello")

    assert [call.args[0] for call in sleep_mock.await_args_list] == [1.0, 2.0, 4.0]


async def test_aclose_calls_shutdown(mock_bot: tuple[AsyncMock, AsyncMock]) -> None:
    _, shutdown_mock = mock_bot
    sender = TelegramSender("test-token")

    await sender.aclose()

    shutdown_mock.assert_awaited_once()
