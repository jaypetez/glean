from __future__ import annotations

from typing import ClassVar

import ollama

from glean.llm.registry import register_embedding_provider
from glean.logging import get_logger
from glean.security.ssrf import is_external_http_url, validate_provider_base_url
from glean.security.ssrf_transport import SSRFGuardedTransport, outbound_timeout

logger = get_logger(__name__)


@register_embedding_provider("ollama")
class OllamaEmbeddingProvider:
    name: ClassVar[str] = "ollama"

    def __init__(
        self,
        model: str = "nomic-embed-text",
        base_url: str | None = None,
        timeout_s: float = 60.0,
        api_key: str | None = None,
    ) -> None:
        del api_key  # unused
        self.model = model
        self.base_url = validate_provider_base_url("ollama", base_url or "http://ollama:11434")
        self.timeout_s = timeout_s
        self._closed = False
        if is_external_http_url(self.base_url):
            logger.warning("ollama_external_http_base_url", base_url=self.base_url)
        self._client = ollama.AsyncClient(
            host=self.base_url,
            timeout=outbound_timeout(read=timeout_s),
            follow_redirects=False,
            transport=SSRFGuardedTransport(allow_private=True),
        )

    async def embed(self, text: str) -> list[float]:
        response = await self._client.embeddings(model=self.model, prompt=text)
        return list(response["embedding"])

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        # ollama.AsyncClient does not expose a public aclose() in the pinned client version.
        client = getattr(self._client, "_client", None)
        if client is not None:
            aclose = getattr(client, "aclose", None)
            if aclose is not None:
                await aclose()
