"""Anthropic LLM provider tests."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from anthropic.types import TextBlock

from glean.llm.anthropic_provider import AnthropicProvider
from glean.llm.common import INJECTION_GUARD_SYSTEM_PROMPT
from glean.sources.base import Item

pytestmark = pytest.mark.asyncio


def _item() -> Item:
    return Item(
        canonical_url="https://example.com/a",
        title="Test",
        body="Body",
        source_type="rss",
        source_name="test",
    )


def _msg(content: str) -> SimpleNamespace:
    """Build an anthropic SDK Message-like object."""
    return SimpleNamespace(content=[TextBlock(text=content, type="text")])


def _provider_with_message(content: str) -> AnthropicProvider:
    provider = AnthropicProvider(model="claude-3", api_key="fake")
    provider._client = SimpleNamespace(
        messages=SimpleNamespace(create=AsyncMock(return_value=_msg(content))),
        close=AsyncMock(),
    )
    return provider


async def test_anthropic_rank() -> None:
    provider = _provider_with_message("0.8")

    score = await provider.rank(_item(), "score")

    assert score == 0.8


async def test_anthropic_rank_sends_expected_message_request() -> None:
    provider = _provider_with_message("0.8")

    await provider.rank(_item(), "score")

    create = provider._client.messages.create
    create.assert_awaited_once()
    kwargs = create.await_args.kwargs
    assert kwargs["model"] == "claude-3"
    assert kwargs["max_tokens"] == 16
    assert kwargs["system"].startswith(INJECTION_GUARD_SYSTEM_PROMPT)
    assert "score" in kwargs["system"]
    assert kwargs["messages"][0]["role"] == "user"
    assert "TITLE: Test" in kwargs["messages"][0]["content"]
    assert "<UNTRUSTED_CONTENT>" in kwargs["messages"][0]["content"]


async def test_anthropic_summarize() -> None:
    provider = _provider_with_message("brief summary")

    out = await provider.summarize(_item(), "summarize")

    assert out == "brief summary"


async def test_anthropic_summarize_uses_default_prompt() -> None:
    provider = _provider_with_message("brief summary")

    await provider.summarize(_item(), "  ")

    kwargs = provider._client.messages.create.await_args.kwargs
    assert kwargs["system"].startswith(INJECTION_GUARD_SYSTEM_PROMPT)
    assert "Summarize the following content in one sentence." in kwargs["system"]
    assert kwargs["max_tokens"] == 256


async def test_anthropic_digest() -> None:
    provider = _provider_with_message("digest header")

    out = await provider.digest([_item()], "write digest")

    assert out == "digest header"


async def test_anthropic_digest_uses_default_prompt() -> None:
    provider = _provider_with_message("digest header")

    await provider.digest([_item()], "")

    kwargs = provider._client.messages.create.await_args.kwargs
    assert kwargs["system"].startswith(INJECTION_GUARD_SYSTEM_PROMPT)
    assert "Write a 1-line digest header for the items below." in kwargs["system"]
    assert kwargs["max_tokens"] == 512
    assert "[1] Test" in kwargs["messages"][0]["content"]


async def test_anthropic_complete_joins_text_blocks_and_strips() -> None:
    provider = AnthropicProvider(model="claude-3", api_key="fake")
    provider._client = SimpleNamespace(
        messages=SimpleNamespace(
            create=AsyncMock(
                return_value=SimpleNamespace(
                    content=[
                        TextBlock(text=" first ", type="text"),
                        SimpleNamespace(text=" ignored "),
                        TextBlock(text="second ", type="text"),
                    ]
                )
            )
        ),
        close=AsyncMock(),
    )

    out = await provider.summarize(_item(), "summarize")

    assert out == "first second"


async def test_anthropic_empty_content_returns_empty_string() -> None:
    provider = _provider_with_message("   ")

    out = await provider.summarize(_item(), "summarize")

    assert out == ""


async def test_anthropic_aclose() -> None:
    provider = _provider_with_message("ok")

    await provider.aclose()

    provider._client.close.assert_awaited_once()


async def test_anthropic_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY is not set"):
        AnthropicProvider(model="claude-3")


async def test_anthropic_uses_env_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-env-key")

    provider = AnthropicProvider(model="claude-3")

    assert provider.model == "claude-3"


async def test_extract_uses_forced_tool_call() -> None:
    provider = AnthropicProvider(model="claude-3", api_key="fake")
    block = SimpleNamespace(name="extract", input={"summary": "S", "ok": True})
    msg = SimpleNamespace(content=[block])
    provider._client = SimpleNamespace(
        messages=SimpleNamespace(create=AsyncMock(return_value=msg)),
        close=AsyncMock(),
    )

    result = await provider.extract(
        _item(),
        "do it",
        {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "ok": {"type": "boolean"},
            },
        },
    )

    assert result == {"summary": "S", "ok": True}
    call = provider._client.messages.create.await_args
    assert call.kwargs["tool_choice"] == {"type": "tool", "name": "extract"}


async def test_extract_returns_empty_when_no_tool_block() -> None:
    provider = AnthropicProvider(model="claude-3", api_key="fake")
    msg = SimpleNamespace(content=[])
    provider._client = SimpleNamespace(
        messages=SimpleNamespace(create=AsyncMock(return_value=msg)),
        close=AsyncMock(),
    )

    result = await provider.extract(_item(), "x", {"type": "object", "properties": {}})

    assert result == {}
