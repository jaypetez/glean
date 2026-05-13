"""Generic HTTP webhook sink."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import httpx

from glean.logging import get_logger
from glean.sinks.registry import register_sink

if TYPE_CHECKING:
    from glean.sinks.base import SendContext
    from glean.sources.base import Item

logger = get_logger(__name__)


@register_sink("webhook")
class WebhookSink:
    """POST a JSON payload to an arbitrary URL."""

    type: ClassVar[str] = "webhook"

    def __init__(
        self,
        url: str,
        *,
        method: str = "POST",
        headers: dict[str, str] | None = None,
        auth_bearer: str | None = None,
        auth_basic: tuple[str, str] | list[str] | None = None,
        timeout_s: float = 30.0,
        required: bool = True,
    ) -> None:
        if not url:
            raise ValueError("webhook sink requires 'url'")
        self.url = url
        self.method = method.upper()
        self.required = required
        self.timeout_s = timeout_s

        merged_headers: dict[str, str] = {"Content-Type": "application/json"}
        if headers:
            merged_headers.update(headers)
        if auth_bearer:
            merged_headers["Authorization"] = f"Bearer {auth_bearer}"
        self._headers = merged_headers

        if auth_basic is not None:
            if isinstance(auth_basic, list):
                if len(auth_basic) != 2:
                    raise ValueError("auth_basic must be [username, password]")
                self._auth: tuple[str, str] | None = (auth_basic[0], auth_basic[1])
            else:
                self._auth = auth_basic
        else:
            self._auth = None

        self._client = httpx.AsyncClient(timeout=timeout_s)

    async def send(self, ctx: SendContext) -> None:
        payload: dict[str, Any] = {
            "feed": ctx.feed,
            "intro": ctx.intro,
            "messages": list(ctx.messages),
            "items": [_item_to_dict(item) for item in ctx.items],
        }
        resp = await self._client.request(
            self.method,
            self.url,
            json=payload,
            headers=self._headers,
            auth=self._auth,
        )
        resp.raise_for_status()
        logger.debug("webhook_sent", feed=ctx.feed, url=self.url, status=resp.status_code)

    async def aclose(self) -> None:
        await self._client.aclose()


def _item_to_dict(item: Item) -> dict[str, Any]:
    """Serialize an Item dataclass to a JSON-safe dict."""
    return {
        "title": item.title,
        "url": item.canonical_url,
        "summary": item.llm_summary or item.summary,
        "source_type": item.source_type,
        "source_name": item.source_name,
        "published_at": item.published_at.isoformat() if item.published_at else None,
        "score": item.score,
        "relevance": item.relevance,
    }
