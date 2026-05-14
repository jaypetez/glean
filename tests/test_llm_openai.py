"""OpenAI LLM provider tests."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from glean.llm.common import INJECTION_GUARD_SYSTEM_PROMPT
from glean.llm.openai_provider import OpenAIProvider
from glean.sources.base import Item

pytestmark = pytest.mark.asyncio


def _item() -> Item:
    return Item(
        canonical_url="https://example.com/a",
        title="T",
        source_type="rss",
        source_name="t",
    )


def _completion(content: str | None) -> SimpleNamespace:
    """Build an OpenAI SDK ChatCompletion-like object."""
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
    )


def _provider_with_completion(content: str | None) -> OpenAIProvider:
    provider = OpenAIProvider(model="gpt-4", api_key="sk-fake")
    provider._client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=AsyncMock(return_value=_completion(content)))
        ),
        close=AsyncMock(),
    )
    return provider


async def test_openai_rank() -> None:
    provider = _provider_with_completion("0.9")

    score = await provider.rank(_item(), "score")

    assert score == 0.9


async def test_openai_rank_sends_expected_chat_request() -> None:
    provider = _provider_with_completion("0.9")

    await provider.rank(_item(), "score")

    create = provider._client.chat.completions.create
    create.assert_awaited_once()
    kwargs = create.await_args.kwargs
    assert kwargs["model"] == "gpt-4"
    assert kwargs["max_tokens"] == 16
    assert kwargs["temperature"] == 0.3
    assert kwargs["messages"][0]["content"].startswith(INJECTION_GUARD_SYSTEM_PROMPT)
    assert "score" in kwargs["messages"][0]["content"]
    assert "TITLE: T" in kwargs["messages"][1]["content"]


async def test_openai_summarize() -> None:
    provider = _provider_with_completion("short summary")

    out = await provider.summarize(_item(), "summarize")

    assert out == "short summary"


async def test_openai_summarize_strips_content() -> None:
    provider = _provider_with_completion("  short summary  ")

    out = await provider.summarize(_item(), "summarize")

    assert out == "short summary"


async def test_openai_summarize_uses_default_prompt() -> None:
    provider = _provider_with_completion("short summary")

    await provider.summarize(_item(), "")

    kwargs = provider._client.chat.completions.create.await_args.kwargs
    system = kwargs["messages"][0]["content"]
    assert system.startswith(INJECTION_GUARD_SYSTEM_PROMPT)
    assert "Summarize the following content in one sentence." in system
    assert kwargs["max_tokens"] == 256


async def test_openai_digest() -> None:
    provider = _provider_with_completion("digest")

    out = await provider.digest([_item()], "header")

    assert out == "digest"


async def test_openai_digest_uses_default_prompt() -> None:
    provider = _provider_with_completion("digest")

    await provider.digest([_item()], "  ")

    kwargs = provider._client.chat.completions.create.await_args.kwargs
    system = kwargs["messages"][0]["content"]
    assert system.startswith(INJECTION_GUARD_SYSTEM_PROMPT)
    assert "Write a 1-line digest header for the items below." in system
    assert kwargs["max_tokens"] == 512
    assert "[1] T" in kwargs["messages"][1]["content"]


async def test_openai_handles_empty_content() -> None:
    provider = _provider_with_completion("")

    out = await provider.summarize(_item(), "summarize")

    assert out == ""


async def test_openai_handles_none_content() -> None:
    provider = _provider_with_completion(None)

    out = await provider.summarize(_item(), "summarize")

    assert out == ""


async def test_openai_aclose() -> None:
    provider = _provider_with_completion("ok")

    await provider.aclose()

    provider._client.close.assert_awaited_once()


async def test_openai_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY is not set"):
        OpenAIProvider(model="gpt-4")


async def test_openai_uses_env_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env-fake")

    provider = OpenAIProvider(model="gpt-4")

    assert provider.model == "gpt-4"


async def test_extract_uses_response_format_json_schema() -> None:
    provider = _provider_with_completion('{"summary": "S"}')

    result = await provider.extract(
        _item(),
        "x",
        {"type": "object", "properties": {"summary": {"type": "string"}}},
    )

    assert result == {"summary": "S"}
    call = provider._client.chat.completions.create.await_args
    assert call.kwargs["response_format"]["type"] == "json_schema"
    assert call.kwargs["response_format"]["json_schema"]["strict"] is True


async def test_extract_returns_empty_on_invalid_json() -> None:
    provider = _provider_with_completion("not json")

    result = await provider.extract(_item(), "x", {"type": "object", "properties": {}})

    assert result == {}
