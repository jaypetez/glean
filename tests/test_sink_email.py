from __future__ import annotations

import datetime as dt
import email.utils
import importlib
import ipaddress
from unittest.mock import AsyncMock, Mock

import pytest
import structlog.testing
from structlog.contextvars import bind_contextvars, reset_contextvars

from glean.config.schema import RenderConfig
from glean.exceptions import SecurityError
from glean.sinks import SendContext, build_sink
from glean.sources.base import Item

pytestmark = pytest.mark.asyncio


def _email_cls():
    return importlib.import_module("glean.sinks.email").EmailSink


def _template_module():
    return importlib.import_module("glean.sinks.email_template")


def _make_item(
    *,
    title: str = "A title",
    canonical_url: str = "https://example.com/a",
    summary: str | None = "A summary",
    llm_summary: str | None = "LLM summary",
    source_name: str = "Example Source",
) -> Item:
    return Item(
        canonical_url=canonical_url,
        title=title,
        summary=summary,
        llm_summary=llm_summary,
        source_type="rss",
        source_name=source_name,
    )


def _make_ctx(
    *,
    feed: str = "daily-digest",
    items: list[Item] | None = None,
    messages: list[str] | None = None,
    intro: str = "Today in glean",
) -> SendContext:
    return SendContext(
        feed=feed,
        items=items if items is not None else [_make_item()],
        messages=messages if messages is not None else ["rendered fragment"],
        intro=intro,
        render=RenderConfig(),
    )


def _make_email_sink(**overrides: object):
    defaults: dict[str, object] = {
        "smtp_host": "smtp.test.local",
        "smtp_port": 587,
        "smtp_user": "user@test.local",
        "smtp_password": "secret",
        "starttls": True,
        "from_addr": "glean <noreply@test.local>",
        "to": ["me@test.local"],
    }
    defaults.update(overrides)
    return _email_cls()(**defaults)


@pytest.fixture
def smtp_mock(monkeypatch: pytest.MonkeyPatch) -> tuple[Mock, Mock]:
    email_module = importlib.import_module("glean.sinks.email")
    smtp_client = Mock()
    smtp_client.connect = AsyncMock()
    smtp_client.starttls = AsyncMock()
    smtp_client.login = AsyncMock()
    smtp_client.send_message = AsyncMock()
    smtp_client.quit = AsyncMock()
    smtp_ctor = Mock(return_value=smtp_client)
    monkeypatch.setattr(email_module.aiosmtplib, "SMTP", smtp_ctor)
    return smtp_ctor, smtp_client


def _sent_message(smtp_client: Mock):
    return smtp_client.send_message.await_args.args[0]


def _payload_for_subtype(message, subtype: str) -> str:
    payload = message.get_payload()
    assert isinstance(payload, list)
    for part in payload:
        if part.get_content_subtype() == subtype:
            decoded = part.get_payload(decode=True)
            assert isinstance(decoded, bytes)
            charset = part.get_content_charset() or "utf-8"
            return decoded.decode(charset)
    raise AssertionError(f"missing MIME part {subtype!r}")


async def test_email_sink_connects_with_starttls(smtp_mock: tuple[Mock, Mock]) -> None:
    smtp_ctor, smtp_client = smtp_mock

    await _make_email_sink().send(_make_ctx())

    # STARTTLS is passed to the SMTP constructor via start_tls=True;
    # aiosmtplib handles the TLS upgrade during connect() automatically.
    smtp_ctor.assert_called_once()
    call_kwargs = smtp_ctor.call_args[1]
    assert call_kwargs.get("start_tls") is True
    assert call_kwargs.get("use_tls") is False


async def test_email_sink_connects_with_implicit_ssl(smtp_mock: tuple[Mock, Mock]) -> None:
    smtp_ctor, smtp_client = smtp_mock

    await _make_email_sink(smtp_port=465, starttls=False, use_ssl=True).send(_make_ctx())

    assert smtp_ctor.call_args.kwargs["use_tls"] is True
    smtp_client.starttls.assert_not_awaited()


async def test_email_sink_connects_plaintext(smtp_mock: tuple[Mock, Mock]) -> None:
    smtp_ctor, smtp_client = smtp_mock

    await _make_email_sink(smtp_port=1025, starttls=False, use_ssl=False).send(_make_ctx())

    assert smtp_ctor.call_args.kwargs["use_tls"] is False
    smtp_client.starttls.assert_not_awaited()


async def test_email_sink_authenticates_with_credentials(smtp_mock: tuple[Mock, Mock]) -> None:
    _, smtp_client = smtp_mock

    await _make_email_sink().send(_make_ctx())

    smtp_client.login.assert_awaited_once_with("user@test.local", "secret")


async def test_email_sink_skips_auth_when_user_empty(smtp_mock: tuple[Mock, Mock]) -> None:
    _, smtp_client = smtp_mock

    await _make_email_sink(smtp_user="", smtp_password="").send(_make_ctx())

    smtp_client.login.assert_not_awaited()


async def test_email_sink_connection_error_propagates_when_required(
    smtp_mock: tuple[Mock, Mock],
) -> None:
    _, smtp_client = smtp_mock
    smtp_client.connect.side_effect = RuntimeError("smtp offline")

    with pytest.raises(RuntimeError, match="smtp offline"):
        await _make_email_sink().send(_make_ctx())


async def test_email_sink_connection_error_swallowed_when_not_required(
    smtp_mock: tuple[Mock, Mock],
) -> None:
    _, smtp_client = smtp_mock
    smtp_client.connect.side_effect = RuntimeError("smtp offline")

    with structlog.testing.capture_logs() as captured_logs:
        await _make_email_sink(required=False).send(_make_ctx())

    assert any(log["event"] == "email_send_failed" for log in captured_logs)


async def test_email_sink_sets_from_to_subject_headers(smtp_mock: tuple[Mock, Mock]) -> None:
    _, smtp_client = smtp_mock

    await _make_email_sink(subject_template="Digest for {feed_name}").send(_make_ctx())
    message = _sent_message(smtp_client)

    assert message["From"] == "glean <noreply@test.local>"
    assert message["To"] == "me@test.local"
    assert message["Subject"] == "Digest for daily-digest"


async def test_email_sink_subject_template_interpolation(smtp_mock: tuple[Mock, Mock]) -> None:
    _, smtp_client = smtp_mock
    ctx = _make_ctx(items=[_make_item(), _make_item(title="B title", canonical_url="https://example.com/b")])
    tokens = bind_contextvars(trace_id="tracebeef")

    try:
        await _make_email_sink(
            subject_template="{feed_name} {date} {item_count} {trace_id}"
        ).send(ctx)
    finally:
        reset_contextvars(**tokens)

    message = _sent_message(smtp_client)
    expected_date = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d")
    assert message["Subject"] == f"daily-digest {expected_date} 2 tracebeef"


async def test_email_sink_subject_template_with_unknown_vars(
    smtp_mock: tuple[Mock, Mock],
) -> None:
    _, smtp_client = smtp_mock

    await _make_email_sink(subject_template="{feed_name} {unknown}").send(_make_ctx())
    message = _sent_message(smtp_client)

    assert message["Subject"] == "daily-digest {unknown}"


async def test_email_sink_multiple_recipients(smtp_mock: tuple[Mock, Mock]) -> None:
    _, smtp_client = smtp_mock

    await _make_email_sink(to=["a@test.local", "b@test.local"]).send(_make_ctx())
    message = _sent_message(smtp_client)

    assert message["To"] == "a@test.local, b@test.local"


async def test_email_sink_custom_headers_x_glean_feed(smtp_mock: tuple[Mock, Mock]) -> None:
    _, smtp_client = smtp_mock

    await _make_email_sink().send(_make_ctx(feed="custom-feed"))
    message = _sent_message(smtp_client)

    assert message["X-Glean-Feed"] == "custom-feed"


async def test_email_sink_custom_headers_x_glean_trace_id(smtp_mock: tuple[Mock, Mock]) -> None:
    _, smtp_client = smtp_mock
    tokens = bind_contextvars(trace_id="cafebabe")

    try:
        await _make_email_sink().send(_make_ctx())
    finally:
        reset_contextvars(**tokens)

    message = _sent_message(smtp_client)
    assert message["X-Glean-Trace-Id"] == "cafebabe"


async def test_email_sink_message_id_and_date_present(smtp_mock: tuple[Mock, Mock]) -> None:
    _, smtp_client = smtp_mock

    await _make_email_sink().send(_make_ctx())
    message = _sent_message(smtp_client)

    assert message["Message-ID"].startswith("<")
    assert message["Message-ID"].endswith("@glean>")
    assert email.utils.parsedate_to_datetime(message["Date"]) is not None


async def test_email_sink_has_html_and_plaintext_parts(smtp_mock: tuple[Mock, Mock]) -> None:
    _, smtp_client = smtp_mock

    await _make_email_sink().send(_make_ctx())
    message = _sent_message(smtp_client)

    assert message.get_content_subtype() == "alternative"
    assert len(message.get_payload()) == 2


async def test_email_sink_html_part_contains_digest_body(smtp_mock: tuple[Mock, Mock]) -> None:
    _, smtp_client = smtp_mock

    await _make_email_sink().send(_make_ctx(items=[_make_item(title="Digest title")]))
    html_body = _payload_for_subtype(_sent_message(smtp_client), "html")

    assert "Digest title" in html_body
    assert "LLM summary" in html_body


async def test_email_sink_plaintext_fallback_readable(smtp_mock: tuple[Mock, Mock]) -> None:
    _, smtp_client = smtp_mock

    await _make_email_sink().send(_make_ctx())
    text_body = _payload_for_subtype(_sent_message(smtp_client), "plain")

    assert "A title" in text_body
    assert "LLM summary" in text_body
    assert "https://example.com/a" in text_body


async def test_email_sink_xss_safe_rendering(smtp_mock: tuple[Mock, Mock]) -> None:
    _, smtp_client = smtp_mock

    await _make_email_sink().send(_make_ctx(items=[_make_item(title="<script>alert(1)</script>")]))
    html_body = _payload_for_subtype(_sent_message(smtp_client), "html")

    assert "<script>" not in html_body
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html_body


async def test_email_template_renders_items_with_titles_and_urls() -> None:
    html = _template_module().render_email_html(
        _make_ctx(items=[_make_item(title="Linked title", canonical_url="https://example.com/linked")])
    )

    assert 'href="https://example.com/linked"' in html
    assert "Linked title" in html


async def test_email_template_renders_intro_as_heading() -> None:
    html = _template_module().render_email_html(_make_ctx(intro="Top stories"))

    assert "<h2" in html
    assert "Top stories" in html


async def test_email_template_inline_css_only() -> None:
    html = _template_module().render_email_html(_make_ctx())

    assert "<style" not in html.lower()
    assert "<link" not in html.lower()


async def test_email_template_no_external_images() -> None:
    html = _template_module().render_email_html(_make_ctx())

    assert "<img" not in html.lower()
    assert "src=\"http" not in html.lower()


async def test_email_template_footer_present() -> None:
    html = _template_module().render_email_html(_make_ctx())

    assert "Powered by glean" in html


async def test_email_sink_rejects_empty_smtp_host() -> None:
    with pytest.raises(ValueError, match="smtp_host"):
        _make_email_sink(smtp_host="")


async def test_email_sink_rejects_empty_to_list() -> None:
    with pytest.raises(ValueError, match="to"):
        _make_email_sink(to=[])


async def test_email_sink_rejects_starttls_and_ssl_both_true() -> None:
    with pytest.raises(ValueError, match="cannot both be true"):
        _make_email_sink(starttls=True, use_ssl=True)


async def test_email_sink_rejects_invalid_port() -> None:
    with pytest.raises(ValueError, match="invalid smtp_port"):
        _make_email_sink(smtp_port=0)

    with pytest.raises(ValueError, match="invalid smtp_port"):
        _make_email_sink(smtp_port=99999)


async def test_email_sink_default_port_587() -> None:
    sink = _email_cls()(
        smtp_host="smtp.test.local",
        smtp_user="",
        smtp_password="",
        from_addr="glean <noreply@test.local>",
        to=["me@test.local"],
    )

    assert sink.smtp_port == 587


async def test_email_sink_allows_private_smtp_hosts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ssrf_module = importlib.import_module("glean.security.ssrf")
    monkeypatch.setattr(ssrf_module, "_resolve", lambda host: [ipaddress.ip_address("172.18.0.25")])

    sink = _make_email_sink(smtp_host="mailpit.docker.internal")

    assert sink.smtp_host == "mailpit.docker.internal"


async def test_email_sink_rejects_metadata_smtp_host() -> None:
    with pytest.raises(SecurityError, match="metadata|cloud"):
        _make_email_sink(smtp_host="169.254.169.254")


async def test_email_sink_builds_from_yaml_config() -> None:
    sink = build_sink(
        {
            "type": "email",
            "smtp_host": "smtp.test.local",
            "from": "glean <noreply@test.local>",
            "to": ["me@test.local"],
        }
    )

    assert sink.type == "email"
    assert sink.from_addr == "glean <noreply@test.local>"


async def test_email_sink_sends_full_digest_context(smtp_mock: tuple[Mock, Mock]) -> None:
    _, smtp_client = smtp_mock
    ctx = _make_ctx(
        items=[_make_item(title="Context title", summary="Context summary", llm_summary=None)],
        messages=["fragment one", "fragment two"],
        intro="Context intro",
    )

    await _make_email_sink().send(ctx)
    html_body = _payload_for_subtype(_sent_message(smtp_client), "html")

    assert "Context intro" in html_body
    assert "Context title" in html_body
    assert "Context summary" in html_body


async def test_email_sink_handles_empty_digest_gracefully(smtp_mock: tuple[Mock, Mock]) -> None:
    _, smtp_client = smtp_mock

    await _make_email_sink().send(_make_ctx(items=[], messages=[], intro="Nothing new"))
    html_body = _payload_for_subtype(_sent_message(smtp_client), "html")

    assert "No new items matched your criteria this run." in html_body


async def test_email_sink_aclose_is_idempotent() -> None:
    sink = _make_email_sink()

    await sink.aclose()
    await sink.aclose()
