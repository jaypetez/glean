"""Ollama LLM provider tests."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from glean.llm.ollama_provider import OllamaProvider
from glean.sources.base import Item

pytestmark = pytest.mark.asyncio


def _item() -> Item:
    return Item(
        canonical_url="https://example.com/a",
        title="Test article title",
        body="Some body content for context.",
        source_type="rss",
        source_name="test",
    )


async def test_ollama_rank_parses_score() -> None:
    provider = OllamaProvider(model="qwen2.5:7b")
    provider._client = AsyncMock()
    provider._client.chat.return_value = {"message": {"content": "0.75"}}

    score = await provider.rank(_item(), "score 0-1")

    assert score == 0.75


async def test_ollama_rank_clamps_out_of_range() -> None:
    provider = OllamaProvider(model="qwen2.5:7b")
    provider._client = AsyncMock()
    provider._client.chat.return_value = {"message": {"content": "1.5"}}

    score = await provider.rank(_item(), "score")

    assert score == 1.0


async def test_ollama_rank_sends_expected_chat_request() -> None:
    provider = OllamaProvider(model="qwen2.5:7b")
    provider._client = AsyncMock()
    provider._client.chat.return_value = {"message": {"content": "0.5"}}

    await provider.rank(_item(), "rank this")

    provider._client.chat.assert_awaited_once()
    kwargs = provider._client.chat.await_args.kwargs
    assert kwargs["model"] == "qwen2.5:7b"
    assert kwargs["options"] == {"temperature": 0.0, "num_predict": 16}
    assert kwargs["messages"][0]["role"] == "system"
    assert "rank this" in kwargs["messages"][0]["content"]
    assert "Test article title" in kwargs["messages"][1]["content"]


async def test_ollama_summarize_returns_content() -> None:
    provider = OllamaProvider(model="qwen2.5:7b")
    provider._client = AsyncMock()
    provider._client.chat.return_value = {"message": {"content": "  short summary text  "}}

    out = await provider.summarize(_item(), "summarize")

    assert out == "short summary text"


async def test_ollama_summarize_handles_empty_content() -> None:
    provider = OllamaProvider(model="qwen2.5:7b")
    provider._client = AsyncMock()
    provider._client.chat.return_value = {"message": {"content": ""}}

    out = await provider.summarize(_item(), "summarize")

    assert out == ""


async def test_ollama_summarize_handles_none_content() -> None:
    provider = OllamaProvider(model="qwen2.5:7b")
    provider._client = AsyncMock()
    provider._client.chat.return_value = {"message": {"content": None}}

    out = await provider.summarize(_item(), "summarize")

    assert out == ""


async def test_ollama_summarize_uses_default_prompt() -> None:
    provider = OllamaProvider(model="qwen2.5:7b")
    provider._client = AsyncMock()
    provider._client.chat.return_value = {"message": {"content": "summary"}}

    await provider.summarize(_item(), "  ")

    kwargs = provider._client.chat.await_args.kwargs
    assert kwargs["messages"][0]["content"] == "Summarize the following content in one sentence."
    assert kwargs["options"] == {"temperature": 0.3, "num_predict": 256}


async def test_ollama_digest_returns_intro() -> None:
    provider = OllamaProvider(model="qwen2.5:7b")
    provider._client = AsyncMock()
    provider._client.chat.return_value = {"message": {"content": "AI news today!"}}

    out = await provider.digest([_item(), _item()], "write a header")

    assert out == "AI news today!"


async def test_ollama_digest_uses_default_prompt() -> None:
    provider = OllamaProvider(model="qwen2.5:7b")
    provider._client = AsyncMock()
    provider._client.chat.return_value = {"message": {"content": "digest"}}

    await provider.digest([_item()], "")

    kwargs = provider._client.chat.await_args.kwargs
    assert kwargs["messages"][0]["content"] == "Write a 1-line digest header for the items below."
    assert "[1] Test article title" in kwargs["messages"][1]["content"]


async def test_ollama_uses_configured_base_url() -> None:
    provider = OllamaProvider(model="m1", base_url="http://custom:11434")

    assert provider.base_url == "http://custom:11434"


async def test_ollama_default_base_url() -> None:
    provider = OllamaProvider(model="m1")

    assert provider.base_url == "http://ollama:11434"


async def test_ollama_aclose_closes_underlying_client() -> None:
    provider = OllamaProvider(model="m1")
    inner = SimpleNamespace(aclose=AsyncMock())
    provider._client = SimpleNamespace(_client=inner)

    await provider.aclose()

    inner.aclose.assert_awaited_once()


async def test_ollama_aclose_handles_missing_inner_client() -> None:
    provider = OllamaProvider(model="m1")
    provider._client = SimpleNamespace()

    await provider.aclose()


async def test_ollama_ignores_api_key_param() -> None:
    provider = OllamaProvider(model="m1", api_key="ignored")

    assert provider.model == "m1"


async def test_extract_returns_parsed_json() -> None:
    provider = OllamaProvider(model="qwen2.5:7b")
    provider._client = AsyncMock()
    provider._client.chat.return_value = {
        "message": {"content": '{"summary": "S", "score": 0.7}'}
    }

    result = await provider.extract(
        _item(),
        "extract this",
        {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "score": {"type": "number"},
            },
        },
    )

    assert result == {"summary": "S", "score": 0.7}
    call = provider._client.chat.await_args
    assert call.kwargs["format"]["type"] == "object"


async def test_extract_returns_empty_dict_on_invalid_json() -> None:
    provider = OllamaProvider(model="x")
    provider._client = AsyncMock()
    provider._client.chat.return_value = {"message": {"content": "not json"}}

    result = await provider.extract(_item(), "x", {"type": "object", "properties": {}})

    assert result == {}
