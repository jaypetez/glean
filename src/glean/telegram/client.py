from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any, Literal

from telegram import Bot, LinkPreviewOptions
from telegram.constants import ParseMode
from telegram.error import RetryAfter, TimedOut

from glean.logging import get_logger

logger = get_logger(__name__)


_PARSE_MODE_MAP: dict[str, str | None] = {
    "html": ParseMode.HTML,
    "markdown_v2": ParseMode.MARKDOWN_V2,
    "plain": None,
}


class TelegramSender:
    def __init__(self, token: str, *, base_url: str | None = None) -> None:
        kwargs: dict[str, Any] = {"token": token}
        if base_url:
            # python-telegram-bot expects base_url/base_file_url to include the /bot prefix.
            normalized = base_url.rstrip("/")
            kwargs["base_url"] = f"{normalized}/bot"
            kwargs["base_file_url"] = f"{normalized}/file/bot"
        self._bot = Bot(**kwargs)

    async def send_digest(
        self,
        chat_id: int | str,
        messages: list[str],
        *,
        style: Literal["html", "markdown_v2", "plain"] = "html",
        link_preview: bool = False,
    ) -> None:
        parse_mode = _PARSE_MODE_MAP.get(style)
        link_opts = LinkPreviewOptions(is_disabled=not link_preview)

        for msg in messages:
            await self._send_with_retry(
                chat_id=chat_id,
                text=msg,
                parse_mode=parse_mode,
                link_preview_options=link_opts,
            )

    async def _send_with_retry(
        self,
        *,
        chat_id: int | str,
        text: str,
        parse_mode: str | None,
        link_preview_options: LinkPreviewOptions,
        max_attempts: int = 4,
    ) -> None:
        delay = 1.0
        for attempt in range(1, max_attempts + 1):
            try:
                await self._bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=parse_mode,
                    link_preview_options=link_preview_options,
                )
                return
            except RetryAfter as exc:
                ra = exc.retry_after
                wait = (ra.total_seconds() if isinstance(ra, timedelta) else float(ra)) + 0.5
                logger.warning(
                    "telegram_rate_limited",
                    chat_id=chat_id,
                    retry_after=wait,
                    attempt=attempt,
                )
                await asyncio.sleep(wait)
            except TimedOut:
                if attempt == max_attempts:
                    raise
                await asyncio.sleep(delay)
                delay *= 2

    async def send_text(
        self,
        chat_id: int | str,
        text: str,
        *,
        style: Literal["html", "markdown_v2", "plain"] = "html",
    ) -> None:
        await self._send_with_retry(
            chat_id=chat_id,
            text=text,
            parse_mode=_PARSE_MODE_MAP.get(style),
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )

    async def aclose(self) -> None:
        await self._bot.shutdown()
