from __future__ import annotations

import os
from typing import TYPE_CHECKING, ClassVar

from glean.logging import get_logger
from glean.security.ssrf import SSRFValidationError, validate_url
from glean.sinks.registry import register_sink
from glean.telegram.client import TelegramSender
from glean.telegram.render import render_digest

if TYPE_CHECKING:
    from glean.sinks.base import SendContext

logger = get_logger(__name__)


@register_sink("telegram")
class TelegramSink:
    type: ClassVar[str] = "telegram"

    def __init__(
        self,
        chat_id: str | int,
        *,
        token: str | None = None,
        base_url: str | None = None,
        required: bool = True,
    ) -> None:
        self.chat_id = chat_id
        self.required = required
        resolved_token = token or os.environ.get("TELEGRAM_BOT_TOKEN")
        if not resolved_token:
            raise ValueError(
                "telegram sink requires a token (set TELEGRAM_BOT_TOKEN or pass 'token' in YAML)"
            )
        resolved_base_url = base_url or os.environ.get("TELEGRAM_BASE_URL")
        if resolved_base_url:
            try:
                validate_url(resolved_base_url)
            except SSRFValidationError as exc:
                raise ValueError(f"telegram base_url: SSRF blocked: {exc}") from exc
        self._sender = TelegramSender(resolved_token, base_url=resolved_base_url)

    async def send(self, ctx: SendContext) -> None:
        messages = ctx.messages or render_digest(ctx.items, intro=ctx.intro, render=ctx.render)
        await self._sender.send_digest(
            self.chat_id,
            messages,
            style=ctx.render.style,
            link_preview=ctx.render.link_preview,
        )

    async def aclose(self) -> None:
        await self._sender.aclose()
