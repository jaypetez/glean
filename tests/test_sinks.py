from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, ClassVar

import pytest

from glean.config.schema import Config
from glean.pipeline.engine import Runner
from glean.sinks import SendContext, register_sink
from glean.sources.base import Item

if TYPE_CHECKING:
    from glean.config.schema import FeedConfig, RenderConfig

pytestmark = pytest.mark.asyncio


@register_sink("fake_sink")
class FakeSink:
    type: ClassVar[str] = "fake_sink"
    calls: ClassVar[list[tuple[str, str, list[str]]]] = []
    closed: ClassVar[list[str]] = []

    def __init__(
        self,
        *,
        name: str = "fake",
        required: bool = True,
        fail: bool = False,
        cancel: bool = False,
    ) -> None:
        self.name = name
        self.required = required
        self.fail = fail
        self.cancel = cancel

    async def send(self, ctx: SendContext) -> None:
        if self.cancel:
            raise asyncio.CancelledError
        if self.fail:
            raise RuntimeError(f"{self.name} failed")
        self.calls.append((self.name, ctx.feed, list(ctx.messages)))

    async def aclose(self) -> None:
        self.closed.append(self.name)


class FakeTelegram:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.sent: list[tuple[int | str, list[str]]] = []

    async def send_digest(
        self,
        chat_id: int | str,
        messages: list[str],
        *,
        style: str = "html",
        link_preview: bool = False,
    ) -> None:
        if self.fail:
            raise RuntimeError("telegram failed")
        self.sent.append((chat_id, list(messages)))

    async def aclose(self) -> None: ...


def _config_with_sink_specs(sink_specs: list[dict[str, Any]]) -> Config:
    return Config.model_validate(
        {
            "feeds": [
                {
                    "name": "sink-test",
                    "schedule": "every 1h",
                    "sinks": sink_specs,
                    "sources": [{"type": "fake"}],
                    "pipeline": ["dedup"],
                }
            ]
        }
    )


def _feed_and_render(cfg: Config) -> tuple[FeedConfig, RenderConfig]:
    feed = cfg.feed("sink-test")
    return feed, feed.effective_render(cfg.defaults)


@pytest.fixture(autouse=True)
def _reset_fake_sink() -> None:
    FakeSink.calls = []
    FakeSink.closed = []


async def test_feed_with_sink_dispatches_to_registered_sink() -> None:
    cfg = _config_with_sink_specs([{"type": "fake_sink", "name": "primary"}])
    feed, render_cfg = _feed_and_render(cfg)
    runner = Runner(cfg, state=object(), telegram=None)  # type: ignore[arg-type]

    await runner._dispatch_sinks(
        feed,
        [Item(canonical_url="https://example.com/a", title="A")],
        ["message"],
        "intro",
        render_cfg,
    )

    assert FakeSink.calls == [("primary", "sink-test", ["message"])]


async def test_feed_with_multiple_sinks_fans_out_to_each_sink() -> None:
    cfg = _config_with_sink_specs(
        [
            {"type": "fake_sink", "name": "one"},
            {"type": "fake_sink", "name": "two"},
        ]
    )
    feed, render_cfg = _feed_and_render(cfg)
    runner = Runner(cfg, state=object(), telegram=None)  # type: ignore[arg-type]

    await runner._dispatch_sinks(feed, [], ["fanout"], "intro", render_cfg)

    assert FakeSink.calls == [
        ("one", "sink-test", ["fanout"]),
        ("two", "sink-test", ["fanout"]),
    ]


async def test_required_sink_failure_propagates() -> None:
    cfg = _config_with_sink_specs([{"type": "fake_sink", "name": "required", "fail": True}])
    feed, render_cfg = _feed_and_render(cfg)
    runner = Runner(cfg, state=object(), telegram=None)  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="required sinks failed: fake_sink"):
        await runner._dispatch_sinks(feed, [], ["message"], "intro", render_cfg)


async def test_optional_sink_failure_is_swallowed() -> None:
    cfg = _config_with_sink_specs(
        [
            {"type": "fake_sink", "name": "optional", "required": False, "fail": True},
            {"type": "fake_sink", "name": "required"},
        ]
    )
    feed, render_cfg = _feed_and_render(cfg)
    runner = Runner(cfg, state=object(), telegram=None)  # type: ignore[arg-type]

    await runner._dispatch_sinks(feed, [], ["message"], "intro", render_cfg)

    assert FakeSink.calls == [("required", "sink-test", ["message"])]


async def test_sink_cancellation_propagates() -> None:
    cfg = _config_with_sink_specs(
        [{"type": "fake_sink", "name": "cancelled", "cancel": True}]
    )
    feed, render_cfg = _feed_and_render(cfg)
    runner = Runner(cfg, state=object(), telegram=None)  # type: ignore[arg-type]

    with pytest.raises(asyncio.CancelledError):
        await runner._dispatch_sinks(feed, [], ["message"], "intro", render_cfg)


async def test_chat_id_only_feed_synthesizes_telegram_sink_and_uses_injected_sender() -> None:
    cfg = Config.model_validate(
        {
            "feeds": [
                {
                    "name": "sink-test",
                    "schedule": "every 1h",
                    "chat_id": -1,
                    "sources": [{"type": "fake"}],
                    "pipeline": ["dedup"],
                }
            ]
        }
    )
    feed, render_cfg = _feed_and_render(cfg)
    fake_tg = FakeTelegram()
    runner = Runner(cfg, state=object(), telegram=fake_tg)  # type: ignore[arg-type]

    assert feed.sinks == [{"type": "telegram", "chat_id": -1}]

    await runner._dispatch_sinks(feed, [], ["legacy"], "intro", render_cfg)

    assert fake_tg.sent == [(-1, ["legacy"])]


async def test_optional_injected_telegram_sink_failure_is_swallowed() -> None:
    cfg = _config_with_sink_specs(
        [{"type": "telegram", "chat_id": -1, "required": False}]
    )
    feed, render_cfg = _feed_and_render(cfg)
    fake_tg = FakeTelegram(fail=True)
    runner = Runner(cfg, state=object(), telegram=fake_tg)  # type: ignore[arg-type]

    await runner._dispatch_sinks(feed, [], ["optional"], "intro", render_cfg)


async def test_multiple_sinks_can_reuse_injected_telegram_sender_without_token() -> None:
    cfg = _config_with_sink_specs(
        [
            {"type": "telegram", "chat_id": -1},
            {"type": "fake_sink", "name": "secondary"},
        ]
    )
    feed, render_cfg = _feed_and_render(cfg)
    fake_tg = FakeTelegram()
    runner = Runner(cfg, state=object(), telegram=fake_tg)  # type: ignore[arg-type]

    await runner._dispatch_sinks(feed, [], ["fanout"], "intro", render_cfg)

    assert fake_tg.sent == [(-1, ["fanout"])]
    assert FakeSink.calls == [("secondary", "sink-test", ["fanout"])]


async def test_empty_sinks_are_rejected() -> None:
    with pytest.raises(ValueError, match="List should have at least 1 item"):
        _config_with_sink_specs([])


async def test_runner_closes_cached_sinks() -> None:
    cfg = _config_with_sink_specs([{"type": "fake_sink", "name": "primary"}])
    feed, render_cfg = _feed_and_render(cfg)
    runner = Runner(cfg, state=object(), telegram=None)  # type: ignore[arg-type]

    await runner._dispatch_sinks(feed, [], ["message"], "intro", render_cfg)
    await runner.aclose()

    assert FakeSink.closed == ["primary"]
