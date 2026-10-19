from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
import respx
from openai.types import CreateEmbeddingResponse

from glean.llm.registry import build_embedding_provider


def test_build_embedding_provider_requires_provider() -> None:
    with pytest.raises(ValueError, match="embedding spec missing 'provider'"):
        build_embedding_provider({})


def test_build_embedding_provider_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError, match="unknown embedding provider"):
        build_embedding_provider({"provider": "missing"})


@respx.mock
async def test_ollama_embedding_provider_returns_embedding_and_closes_idempotently() -> None:
    route = respx.post("http://ollama:11434/api/embeddings").mock(
        return_value=httpx.Response(200, json={"embedding": [0.1, 0.2, 0.3]})
    )
    provider = build_embedding_provider({"provider": "ollama"})

    try:
        embedding = await provider.embed("hello from glean")

        assert embedding == [0.1, 0.2, 0.3]
        assert len(embedding) == 3
        assert route.called is True
        assert json.loads(route.calls.last.request.content) == {
            "model": "nomic-embed-text",
            "prompt": "hello from glean",
        }
    finally:
        await provider.aclose()
        await provider.aclose()


def _openai_provider() -> Any:
    return build_embedding_provider(
        {
            "provider": "openai",
            "api_key": "test-key",
            "base_url": "https://api.openai.test/v1",
        }
    )


def _embedding_response(data: list[dict[str, Any]]) -> CreateEmbeddingResponse:
    # openai>=3 rides on httpx2, which respx cannot intercept; stub the SDK call instead.
    return CreateEmbeddingResponse.model_validate(
        {
            "data": data,
            "model": "text-embedding-3-small",
            "object": "list",
            "usage": {"prompt_tokens": 3, "total_tokens": 3},
        }
    )


async def test_openai_embedding_provider_returns_embedding_and_closes_idempotently() -> None:
    provider = _openai_provider()
    create = AsyncMock(
        return_value=_embedding_response(
            [{"object": "embedding", "embedding": [0.1, 0.2, 0.3, 0.4], "index": 0}]
        )
    )
    provider._client.embeddings.create = create

    try:
        embedding = await provider.embed("hello from glean")

        assert embedding == [0.1, 0.2, 0.3, 0.4]
        create.assert_awaited_once_with(model="text-embedding-3-small", input="hello from glean")
    finally:
        await provider.aclose()
        await provider.aclose()


async def test_openai_embedding_provider_raises_when_response_has_no_embeddings() -> None:
    provider = _openai_provider()
    provider._client.embeddings.create = AsyncMock(return_value=_embedding_response([]))

    try:
        with pytest.raises(RuntimeError, match="returned no data"):
            await provider.embed("hello from glean")
    finally:
        await provider.aclose()
