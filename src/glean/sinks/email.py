"""Email (SMTP) sink — delivers digests as styled HTML email."""

from __future__ import annotations

import contextlib
import datetime as dt
import email.utils
import uuid
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import TYPE_CHECKING, ClassVar

import aiosmtplib
from structlog.contextvars import get_contextvars

from glean.logging import get_logger
from glean.security.scrub import scrub
from glean.security.ssrf import validate_url
from glean.sinks.email_template import render_email_html, render_email_plaintext
from glean.sinks.registry import register_sink

if TYPE_CHECKING:
    from glean.sinks.base import SendContext

logger = get_logger(__name__)


@register_sink("email")
class EmailSink:
    type: ClassVar[str] = "email"

    def __init__(
        self,
        *,
        smtp_host: str,
        smtp_port: int | str = 587,
        smtp_user: str = "",
        smtp_password: str = "",
        starttls: bool = True,
        use_ssl: bool = False,
        from_addr: str | None = None,
        to: list[str] | None = None,
        subject_template: str = "[glean] {feed_name} digest — {date}",
        required: bool = True,
        **kwargs: object,
    ) -> None:
        # `from` is a YAML-facing key, but `from` is a Python keyword.
        self.from_addr = from_addr or str(kwargs.get("from", ""))
        if not smtp_host:
            raise ValueError("email sink requires 'smtp_host'")
        if not self.from_addr:
            raise ValueError("email sink requires 'from' (sender address)")
        if not to:
            raise ValueError("email sink requires 'to' (list of recipient addresses)")
        if starttls and use_ssl:
            raise ValueError("email sink: 'starttls' and 'use_ssl' cannot both be true")
        port = int(smtp_port)
        if port < 1 or port > 65535:
            raise ValueError(f"email sink: invalid smtp_port {smtp_port}")
        validate_url(f"https://{smtp_host}:{port}/", allow_private=True)

        self.smtp_host = smtp_host
        self.smtp_port = port
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password
        self.starttls = starttls
        self.use_ssl = use_ssl
        self.to = list(to)
        self.subject_template = subject_template
        self.required = required

    async def send(self, ctx: SendContext) -> None:
        subject = self._interpolate_subject(ctx)
        html_body = render_email_html(ctx)
        text_body = render_email_plaintext(ctx)
        message = MIMEMultipart("alternative")
        message["From"] = self.from_addr
        message["To"] = ", ".join(self.to)
        message["Subject"] = subject
        message["Date"] = email.utils.formatdate(localtime=True)
        message["Message-ID"] = f"<{uuid.uuid4()}@glean>"
        message["X-Glean-Feed"] = ctx.feed
        trace_id = _current_trace_id()
        if trace_id is not None:
            message["X-Glean-Trace-Id"] = trace_id

        message.attach(MIMEText(text_body, "plain", "utf-8"))
        message.attach(MIMEText(html_body, "html", "utf-8"))

        smtp = aiosmtplib.SMTP(
            hostname=self.smtp_host,
            port=self.smtp_port,
            use_tls=self.use_ssl,
            start_tls=self.starttls,
        )
        connected = False
        try:
            await smtp.connect()
            connected = True
            if self.smtp_user:
                await smtp.login(self.smtp_user, self.smtp_password)
            await smtp.send_message(message)
        except Exception as exc:
            if self.required:
                raise
            logger.warning(
                "email_send_failed",
                feed=ctx.feed,
                err_type=type(exc).__name__,
                err=scrub(str(exc))[:500] or "(no message)",
            )
            return
        finally:
            if connected:
                with contextlib.suppress(Exception):
                    await smtp.quit()

        logger.info(
            "email_sent",
            feed=ctx.feed,
            recipient_count=len(self.to),
            subject=subject,
        )

    def _interpolate_subject(self, ctx: SendContext) -> str:
        now = dt.datetime.now(dt.UTC)
        replacements = {
            "feed_name": ctx.feed,
            "date": now.strftime("%Y-%m-%d"),
            "item_count": str(len(ctx.items)),
            "trace_id": _current_trace_id() or "",
        }
        result = self.subject_template
        for key, value in replacements.items():
            result = result.replace(f"{{{key}}}", value)
        return result

    async def aclose(self) -> None:
        # SMTP connections are opened and closed per send(); no persistent resource to release.
        pass


def _current_trace_id() -> str | None:
    trace_id = get_contextvars().get("trace_id")
    if isinstance(trace_id, str) and trace_id:
        return trace_id
    return None
