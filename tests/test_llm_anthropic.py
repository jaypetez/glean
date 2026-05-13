"""Anthropic LLM provider tests."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from anthropic.types import TextBlock

from glean.llm.anthropic_provider import AnthropicProvider
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
    assert "score" in kwargs["system"]
    assert kwargs["messages"] == [{"role": "user", "content": "TITLE: Test\nSOURCE: test\nURL: https://example.com/a\nBODY:\nBody"}]


async def test_anthropic_summarize() -> None:
    provider = _provider_with_message("brief summary")

    out = await provider.summarize(_item(), "summarize")

    assert out == "brief summary"


async def test_anthropic_summarize_uses_default_prompt() -> None:
    provider = _provider_with_message("brief summary")

    await provider.summarize(_item(), "  ")

    kwargs = provider._client.messages.create.await_args.kwargs
    assert kwargs["system"] == "Summarize the following content in one sentence."
    assert kwargs["max_tokens"] == 256


async def test_anthropic_digest() -> None:
    provider = _provider_with_message("digest header")

    out = await provider.digest([_item()], "write digest")

    assert out == "digest header"


async def test_anthropic_digest_uses_default_prompt() -> None:
    provider = _provider_with_message("digest header")

    await provider.digest([_item()], "")

    kwargs = provider._client.messages.create.await_args.kwargs
    assert kwargs["system"] == "Write a 1-line digest header for the items below."
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
