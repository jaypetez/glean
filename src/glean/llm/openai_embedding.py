from __future__ import annotations

import os
from typing import ClassVar

import httpx
import openai
from openai.types import CreateEmbeddingResponse

from glean.llm.registry import register_embedding_provider
from glean.security.ssrf import is_localhost_url, validate_provider_base_url
from glean.security.ssrf_transport import SSRFGuardedTransport, outbound_timeout


@register_embedding_provider("openai")
class OpenAIEmbeddingProvider:
    name: ClassVar[str] = "openai"

    def __init__(
        self,
        model: str = "text-embedding-3-small",
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_s: float = 60.0,
    ) -> None:
        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        self.model = model
        self._closed = False
        validated_base_url = (
            validate_provider_base_url("openai", base_url) if base_url is not None else None
        )
        allow_private = bool(validated_base_url and is_localhost_url(validated_base_url))
        timeout = outbound_timeout(read=timeout_s)
        http_client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            transport=SSRFGuardedTransport(allow_private=allow_private),
        )
        self._client = openai.AsyncOpenAI(
            api_key=key,
            base_url=validated_base_url,
            timeout=timeout,
            http_client=http_client,
        )

    async def embed(self, text: str) -> list[float]:
        try:
            response: CreateEmbeddingResponse = await self._client.embeddings.create(
                model=self.model,
                input=text,
            )
        except ValueError as exc:
            if "No embedding data received" in str(exc):
                raise RuntimeError("OpenAI embeddings API returned no data") from exc
            raise
        if not response.data:
            raise RuntimeError("OpenAI embeddings API returned no data")
        return list(response.data[0].embedding)

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._client.close()
