from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

import httpx
import pytest
import respx

from glean.config.schema import Config, RenderConfig
from glean.pipeline.engine import Runner
from glean.sinks import SendContext, build_sink, register_sink
from glean.sources.base import Item

if TYPE_CHECKING:
    from glean.config.schema import FeedConfig

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

    async def aclose(self) -> None:
        pass


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
    cfg = _config_with_sink_specs([{"type": "fake_sink", "name": "cancelled", "cancel": True}])
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


async def test_telegram_base_url_env_uses_sink_constructor(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_BASE_URL", "http://mock-telegram:8001")
    cfg = _config_with_sink_specs([{"type": "telegram", "chat_id": -1}])
    feed, render_cfg = _feed_and_render(cfg)
    built_specs: list[dict[str, Any]] = []

    def fake_build_sink(spec: dict[str, Any]) -> FakeSink:
        built_specs.append(spec)
        return FakeSink(name="telegram-plugin")

    monkeypatch.setattr("glean.pipeline.engine.build_sink", fake_build_sink)
    fake_tg = FakeTelegram()
    runner = Runner(cfg, state=object(), telegram=fake_tg)  # type: ignore[arg-type]

    await runner._dispatch_sinks(feed, [], ["message"], "intro", render_cfg)

    assert built_specs == [{"type": "telegram", "chat_id": -1}]
    assert fake_tg.sent == []
    assert FakeSink.calls == [("telegram-plugin", "sink-test", ["message"])]


async def test_optional_injected_telegram_sink_failure_is_swallowed() -> None:
    cfg = _config_with_sink_specs([{"type": "telegram", "chat_id": -1, "required": False}])
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


def _ctx() -> SendContext:
    items = [
        Item(
            canonical_url="https://example.com/a",
            title="A title",
            source_type="rss",
            source_name="ex",
            summary="A summary",
            llm_summary="LLM summary A",
        ),
        Item(
            canonical_url="https://example.com/b",
            title="B title",
            source_type="rss",
            source_name="ex",
        ),
    ]
    return SendContext(
        feed="t1",
        items=items,
        messages=["raw msg"],
        intro="<b>intro</b>",
        render=RenderConfig(),
    )


def _make_ctx(items: list[Item] | None = None) -> SendContext:
    items = items or [
        Item(
            canonical_url="https://example.com/a",
            title="A",
            source_type="rss",
            source_name="ex",
        ),
        Item(
            canonical_url="https://example.com/b",
            title="B",
            source_type="rss",
            source_name="ex",
        ),
    ]
    return SendContext(
        feed="t1",
        items=items,
        messages=["msg1", "msg2"],
        intro="intro line",
        render=RenderConfig(),
    )


@respx.mock
async def test_discord_sink_posts_webhook() -> None:
    route = respx.post("https://discord.com/api/webhooks/123/abc").mock(
        return_value=httpx.Response(204)
    )
    sink = build_sink(
        {
            "type": "discord",
            "webhook_url": "https://discord.com/api/webhooks/123/abc",
        }
    )
    try:
        await sink.send(_ctx())
    finally:
        await sink.aclose()

    assert route.called
    payload = route.calls.last.request.read().decode()
    body = json.loads(payload)
    assert "**A title**" in body["content"]
    assert "**B title**" in body["content"]


@respx.mock
async def test_discord_sink_strips_html_in_intro() -> None:
    route = respx.post("https://discord.com/api/webhooks/123/abc").mock(
        return_value=httpx.Response(204)
    )
    sink = build_sink(
        {
            "type": "discord",
            "webhook_url": "https://discord.com/api/webhooks/123/abc",
        }
    )
    try:
        await sink.send(_ctx())
    finally:
        await sink.aclose()

    body = json.loads(route.calls.last.request.read().decode())
    assert "<b>" not in body["content"]
    assert "**intro**" in body["content"]


@respx.mock
async def test_discord_sink_escapes_markdown_and_drops_unsafe_url() -> None:
    route = respx.post("https://discord.com/api/webhooks/123/abc").mock(
        return_value=httpx.Response(204)
    )
    item = Item(
        canonical_url="javascript:alert(1)",
        title="[click](evil) *bold* @everyone <@everyone>",
        source_type="rss",
        source_name="ex",
        llm_summary="summary <b>_here_</b> `code` | > quote",
    )
    sink = build_sink(
        {
            "type": "discord",
            "webhook_url": "https://discord.com/api/webhooks/123/abc",
        }
    )
    try:
        await sink.send(
            SendContext(
                feed="t1",
                items=[item],
                messages=["raw msg"],
                intro="",
                render=RenderConfig(),
            )
        )
    finally:
        await sink.aclose()

    body = json.loads(route.calls.last.request.read().decode())
    assert body["allowed_mentions"] == {"parse": []}
    assert r"**\[click\]\(evil\) \*bold\* \@everyone \<\@everyone\>**" in body["content"]
    assert r"summary \_here\_ \`code\` \| \> quote" in body["content"]
    assert "<b>" not in body["content"]
    assert "javascript:alert(1)" not in body["content"]


@respx.mock
async def test_ntfy_sink_posts_with_headers() -> None:
    route = respx.post("https://ntfy.sh/my-topic").mock(
        return_value=httpx.Response(200, json={"id": "1"})
    )
    sink = build_sink(
        {
            "type": "ntfy",
            "topic": "my-topic",
            "priority": 4,
            "tags": ["news", "ai"],
            "token": "tk_secret",
        }
    )
    try:
        await sink.send(_ctx())
    finally:
        await sink.aclose()

    assert route.called
    req = route.calls.last.request
    assert req.headers["Priority"] == "4"
    assert req.headers["Tags"] == "news,ai"
    assert req.headers["Authorization"] == "Bearer tk_secret"
    assert "A title" in req.content.decode()


@respx.mock
async def test_ntfy_sink_uses_custom_base_url() -> None:
    route = respx.post("https://ntfy.example.com/my-topic").mock(return_value=httpx.Response(200))
    sink = build_sink(
        {
            "type": "ntfy",
            "topic": "my-topic",
            "base_url": "https://ntfy.example.com",
        }
    )
    try:
        await sink.send(_ctx())
    finally:
        await sink.aclose()

    assert route.called


@respx.mock
async def test_ntfy_sink_encodes_non_ascii_title() -> None:
    route = respx.post("https://ntfy.sh/my-topic").mock(return_value=httpx.Response(200))
    sink = build_sink({"type": "ntfy", "topic": "my-topic"})
    ctx = SendContext(
        feed="t1",
        items=_ctx().items,
        messages=["raw msg"],
        intro="🧠 <b>AI news</b>\nthis hour",
        render=RenderConfig(),
    )
    try:
        await sink.send(ctx)
    finally:
        await sink.aclose()

    assert route.called
    title = route.calls.last.request.headers["Title"]
    assert title.startswith("=?utf-8?b?")
    assert "\n" not in title


@respx.mock
async def test_discord_sink_splits_oversized_item_blocks() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content)["content"])
        return httpx.Response(204)

    respx.post("https://discord.com/api/webhooks/123/abc").mock(side_effect=handler)
    item = Item(
        canonical_url="https://example.com/long",
        title="Long title",
        source_type="rss",
        source_name="ex",
        llm_summary="x" * 2500,
    )
    sink = build_sink(
        {
            "type": "discord",
            "webhook_url": "https://discord.com/api/webhooks/123/abc",
        }
    )
    try:
        await sink.send(
            SendContext(
                feed="t1",
                items=[item],
                messages=["raw msg"],
                intro="",
                render=RenderConfig(),
            )
        )
    finally:
        await sink.aclose()

    assert len(calls) == 2
    assert all(len(call) <= 2000 for call in calls)


@respx.mock
async def test_slack_sink_splits_oversized_item_blocks() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content)["text"])
        return httpx.Response(200, text="ok")

    respx.post("https://hooks.slack.com/services/TABC123/BDEF456/XYZ789").mock(side_effect=handler)
    item = Item(
        canonical_url="https://example.com/long",
        title="Long title",
        source_type="rss",
        source_name="ex",
        llm_summary="x" * 3500,
    )
    sink = build_sink(
        {
            "type": "slack",
            "webhook_url": "https://hooks.slack.com/services/TABC123/BDEF456/XYZ789",
        }
    )
    try:
        await sink.send(
            SendContext(
                feed="t1",
                items=[item],
                messages=["raw msg"],
                intro="",
                render=RenderConfig(),
            )
        )
    finally:
        await sink.aclose()

    assert len(calls) == 2
    assert all(len(call) <= 3000 for call in calls)


@respx.mock
async def test_slack_sink_posts_webhook() -> None:
    route = respx.post("https://hooks.slack.com/services/TABC123/BDEF456/XYZ789").mock(
        return_value=httpx.Response(200, text="ok")
    )
    sink = build_sink(
        {
            "type": "slack",
            "webhook_url": "https://hooks.slack.com/services/TABC123/BDEF456/XYZ789",
            "channel": "#news",
            "icon_emoji": ":robot_face:",
        }
    )
    try:
        await sink.send(_ctx())
    finally:
        await sink.aclose()

    assert route.called
    body = json.loads(route.calls.last.request.read().decode())
    assert body["channel"] == "#news"
    assert body["icon_emoji"] == ":robot_face:"
    assert "*<https://example.com/a|A title>*" in body["text"]


@respx.mock
async def test_slack_sink_escapes_entities_formatting_and_drops_unsafe_url() -> None:
    route = respx.post("https://hooks.slack.com/services/TABC123/BDEF456/XYZ789").mock(
        return_value=httpx.Response(200, text="ok")
    )
    item = Item(
        canonical_url="javascript:alert(1)",
        title="*bold* <script> _x_",
        source_type="rss",
        source_name="ex",
        llm_summary="`code` & <script> ~strike~",
    )
    sink = build_sink(
        {
            "type": "slack",
            "webhook_url": "https://hooks.slack.com/services/TABC123/BDEF456/XYZ789",
        }
    )
    try:
        await sink.send(
            SendContext(
                feed="t1",
                items=[item],
                messages=["raw msg"],
                intro="",
                render=RenderConfig(),
            )
        )
    finally:
        await sink.aclose()

    body = json.loads(route.calls.last.request.read().decode())
    assert r"*\*bold\* &lt;script&gt; \_x\_*" in body["text"]
    assert r"\`code\` &amp;  \~strike\~" in body["text"]
    assert "&lt;script&gt;" not in body["text"].split("\n", maxsplit=1)[1]
    assert "javascript:alert(1)" not in body["text"]


@respx.mock
async def test_slack_sink_escapes_link_url_delimiters() -> None:
    route = respx.post("https://hooks.slack.com/services/TABC123/BDEF456/XYZ789").mock(
        return_value=httpx.Response(200, text="ok")
    )
    item = Item(
        canonical_url="https://example.com/a>b|c&d",
        title="safe",
        source_type="rss",
        source_name="ex",
    )
    sink = build_sink(
        {
            "type": "slack",
            "webhook_url": "https://hooks.slack.com/services/TABC123/BDEF456/XYZ789",
        }
    )
    try:
        await sink.send(
            SendContext(
                feed="t1",
                items=[item],
                messages=["raw msg"],
                intro="",
                render=RenderConfig(),
            )
        )
    finally:
        await sink.aclose()

    body = json.loads(route.calls.last.request.read().decode())
    assert "*<https://example.com/a&gt;b%7Cc&amp;d|safe>*" in body["text"]


async def test_each_sink_raises_on_missing_required_field() -> None:
    with pytest.raises(ValueError):
        build_sink({"type": "discord"})
    with pytest.raises(ValueError):
        build_sink({"type": "ntfy"})
    with pytest.raises(ValueError):
        build_sink({"type": "slack"})


@pytest.mark.parametrize(
    "spec",
    [
        {"type": "discord", "webhook_url": "http://169.254.169.254/hook"},
        {"type": "slack", "webhook_url": "http://10.0.0.1/hook"},
        {"type": "ntfy", "topic": "alerts", "base_url": "http://127.0.0.1:8080"},
        {"type": "webhook", "url": "file:///etc/passwd"},
    ],
)
async def test_http_sinks_reject_malicious_urls(spec: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        build_sink(spec)


async def test_webhook_sink_rejects_disallowed_method() -> None:
    with pytest.raises(ValueError, match="method"):
        build_sink({"type": "webhook", "url": "https://example.com/hook", "method": "DELETE"})


@pytest.mark.asyncio
@respx.mock
async def test_webhook_sink_posts_payload() -> None:
    route = respx.post("https://example.com/hook").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    sink = build_sink({"type": "webhook", "url": "https://example.com/hook"})
    try:
        await sink.send(_make_ctx())
    finally:
        await sink.aclose()

    assert route.called
    request = route.calls.last.request
    payload = json.loads(request.content)
    assert payload["feed"] == "t1"
    assert payload["intro"] == "intro line"
    assert len(payload["items"]) == 2
    assert payload["items"][0]["url"] == "https://example.com/a"


@pytest.mark.asyncio
@respx.mock
async def test_webhook_sink_raises_on_http_error() -> None:
    respx.post("https://example.com/hook").mock(return_value=httpx.Response(500, text="oops"))
    sink = build_sink({"type": "webhook", "url": "https://example.com/hook"})
    try:
        with pytest.raises(httpx.HTTPStatusError):
            await sink.send(_make_ctx())
    finally:
        await sink.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_webhook_sink_supports_bearer_auth() -> None:
    route = respx.post("https://example.com/hook").mock(return_value=httpx.Response(200))
    sink = build_sink(
        {
            "type": "webhook",
            "url": "https://example.com/hook",
            "auth_bearer": "secret-token",
        }
    )
    try:
        await sink.send(_make_ctx())
    finally:
        await sink.aclose()
    assert route.calls.last.request.headers["Authorization"] == "Bearer secret-token"


@pytest.mark.asyncio
@respx.mock
async def test_webhook_sink_supports_basic_auth_list() -> None:
    route = respx.post("https://example.com/hook").mock(return_value=httpx.Response(200))
    sink = build_sink(
        {
            "type": "webhook",
            "url": "https://example.com/hook",
            "auth_basic": ["user", "pass"],
        }
    )
    try:
        await sink.send(_make_ctx())
    finally:
        await sink.aclose()
    assert route.calls.last.request.headers["Authorization"] == "Basic dXNlcjpwYXNz"


async def test_webhook_sink_rejects_invalid_basic_auth_list() -> None:
    with pytest.raises(ValueError, match="auth_basic must be"):
        build_sink(
            {
                "type": "webhook",
                "url": "https://example.com/hook",
                "auth_basic": ["only-user"],
            }
        )


@pytest.mark.asyncio
async def test_file_sink_text_format(tmp_path: Path) -> None:
    out = tmp_path / "out.txt"
    sink = build_sink({"type": "file", "path": str(out)})
    await sink.send(_make_ctx())
    await sink.aclose()
    content = out.read_text(encoding="utf-8")
    assert "msg1" in content
    assert "msg2" in content
    assert "---" in content


@pytest.mark.asyncio
async def test_file_sink_write_does_not_block_event_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from glean.sinks.file import FileSink

    out = tmp_path / "out.txt"
    sink = build_sink({"type": "file", "path": str(out)})
    start = time.perf_counter()
    first_tick_at: float | None = None

    async def ticker() -> None:
        nonlocal first_tick_at
        await asyncio.sleep(0.01)
        first_tick_at = time.perf_counter() - start

    def slow_write(self: FileSink, ctx: SendContext) -> None:
        time.sleep(0.2)
        self.path.write_text(ctx.messages[0], encoding="utf-8")

    monkeypatch.setattr(FileSink, "_write_text", slow_write)
    await asyncio.gather(sink.send(_make_ctx()), ticker())
    await sink.aclose()

    assert first_tick_at is not None
    assert first_tick_at < 0.1


@pytest.mark.asyncio
async def test_file_sink_jsonl_format(tmp_path: Path) -> None:
    out = tmp_path / "out.jsonl"
    sink = build_sink({"type": "file", "path": str(out), "format": "jsonl"})
    await sink.send(_make_ctx())
    await sink.aclose()
    lines = out.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    row = json.loads(lines[0])
    assert row["feed"] == "t1"
    assert row["title"] == "A"


@pytest.mark.asyncio
async def test_file_sink_markdown_format(tmp_path: Path) -> None:
    out = tmp_path / "out.md"
    sink = build_sink({"type": "file", "path": str(out), "format": "markdown"})
    await sink.send(_make_ctx())
    await sink.aclose()
    content = out.read_text(encoding="utf-8")
    assert "## intro line" in content
    assert "### A" in content
    assert "### B" in content


@pytest.mark.asyncio
async def test_file_sink_markdown_drops_unsafe_url(tmp_path: Path) -> None:
    out = tmp_path / "out.md"
    sink = build_sink({"type": "file", "path": str(out), "format": "markdown"})
    await sink.send(
        _make_ctx(
            [
                Item(
                    canonical_url="javascript:alert(1)",
                    title="Unsafe",
                    source_type="rss",
                    source_name="ex",
                )
            ]
        )
    )
    await sink.aclose()
    content = out.read_text(encoding="utf-8")
    assert "javascript:alert(1)" not in content
    assert "[link](" not in content


@pytest.mark.asyncio
async def test_file_sink_appends(tmp_path: Path) -> None:
    out = tmp_path / "out.txt"
    sink = build_sink({"type": "file", "path": str(out)})
    await sink.send(_make_ctx())
    await sink.send(_make_ctx())
    await sink.aclose()
    content = out.read_text(encoding="utf-8")
    assert content.count("msg1") == 2
