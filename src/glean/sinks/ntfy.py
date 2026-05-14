"""ntfy.sh sink."""
from __future__ import annotations

import base64
import re
from typing import TYPE_CHECKING, ClassVar

import httpx

from glean.logging import get_logger
from glean.security.ssrf import validate_url
from glean.security.ssrf_transport import SSRFGuardedTransport, outbound_timeout
from glean.sinks.registry import register_sink

if TYPE_CHECKING:
    from glean.sinks.base import SendContext

logger = get_logger(__name__)

NTFY_MAX_BODY = 4096
NTFY_MAX_TITLE = 200
_TAG_RE = re.compile(r"<[^>]+>")


@register_sink("ntfy")
class NtfySink:
    """POST messages to ntfy.sh (or self-hosted ntfy server)."""

    type: ClassVar[str] = "ntfy"

    def __init__(
        self,
        topic: str = "",
        *,
        base_url: str = "https://ntfy.sh",
        token: str | None = None,
        priority: str | int | None = None,
        tags: list[str] | None = None,
        timeout_s: float = 30.0,
        required: bool = True,
    ) -> None:
        if not topic:
            raise ValueError("ntfy sink requires 'topic'")
        self.topic = topic
        self.base_url = validate_url(base_url).rstrip("/")
        self.token = token
        self.priority = str(priority) if priority is not None else None
        self.tags = tags
        self.required = required
        self._client = httpx.AsyncClient(
            timeout=outbound_timeout(read=timeout_s),
            follow_redirects=False,
            transport=SSRFGuardedTransport(allow_private=False),
        )

    async def send(self, ctx: SendContext) -> None:
        title = _ntfy_header(_strip_html(ctx.intro) if ctx.intro else f"glean: {ctx.feed}")
        body = _render_plain(ctx)
        if len(body) > NTFY_MAX_BODY:
            body = body[: NTFY_MAX_BODY - 1] + "…"

        headers: dict[str, str] = {"Title": title}
        if self.priority:
            headers["Priority"] = self.priority
        if self.tags:
            headers["Tags"] = ",".join(self.tags)
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        url = f"{self.base_url}/{self.topic}"
        resp = await self._client.post(url, content=body.encode("utf-8"), headers=headers)
        resp.raise_for_status()
        logger.debug("ntfy_sent", feed=ctx.feed, topic=self.topic)

    async def aclose(self) -> None:
        await self._client.aclose()


def _render_plain(ctx: SendContext) -> str:
    parts: list[str] = []
    for item in ctx.items:
        title = item.title or "(untitled)"
        summary = item.llm_summary or item.summary or ""
        url = item.canonical_url or ""
        block = title
        if summary:
            block += "\n" + _strip_html(summary)
        if url:
            block += "\n" + url
        parts.append(block)
    return "\n\n".join(parts)


def _strip_html(text: str) -> str:
    return _TAG_RE.sub("", text).strip()


def _ntfy_header(text: str) -> str:
    title = " ".join(text.split())[:NTFY_MAX_TITLE]
    try:
        title.encode("ascii")
    except UnicodeEncodeError:
        encoded = base64.b64encode(title.encode("utf-8")).decode("ascii")
        return f"=?utf-8?b?{encoded}?="
    return title
