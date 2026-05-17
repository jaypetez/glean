"""Append-only file sink for archival/debugging."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Literal

from glean.logging import get_logger
from glean.sinks.escape import safe_url
from glean.sinks.registry import register_sink

if TYPE_CHECKING:
    from glean.sinks.base import SendContext

logger = get_logger(__name__)

_DEFAULT_ROOTS = ["/data", "/tmp/glean"]  # noqa: S108 # nosec
_MAX_PATH_SEGMENTS = 10


def validate_file_sink_path(path: str) -> Path:
    resolved = Path(path).resolve()
    allowed_roots = _allowed_roots()
    matched_root = next(
        (root for root in allowed_roots if _is_under_allowed_root(resolved, root)), None
    )
    if matched_root is None:
        raise ValueError(f"file sink path {resolved} is outside allowed roots {allowed_roots}")
    if resolved == matched_root:
        raise ValueError(f"file sink path {resolved} must name a file below an allowed root")

    relative_parts = _relative_parts(resolved, matched_root)
    if len(relative_parts) > _MAX_PATH_SEGMENTS:
        raise ValueError(
            f"file sink path {resolved} has more than {_MAX_PATH_SEGMENTS} path segments"
        )
    return resolved


def _allowed_roots() -> list[Path]:
    roots_env = os.environ.get("GLEAN_FILE_SINK_ROOTS", "").strip()
    raw_roots = roots_env.split(",") if roots_env else _DEFAULT_ROOTS
    allowed_roots = [Path(root.strip()).resolve() for root in raw_roots if root.strip()]
    if not allowed_roots:
        raise ValueError("GLEAN_FILE_SINK_ROOTS must contain at least one path")
    return allowed_roots


def _is_under_allowed_root(resolved: Path, root: Path) -> bool:
    resolved_str = os.path.normcase(str(resolved))
    root_str = os.path.normcase(str(root))
    return resolved_str.startswith(root_str + os.sep) or resolved_str == root_str


def _relative_parts(resolved: Path, root: Path) -> tuple[str, ...]:
    if resolved == root:
        return ()
    relative = os.path.relpath(resolved, root)
    return Path(relative).parts


@register_sink("file")
class FileSink:
    """Append rendered output to a local file."""

    type: ClassVar[str] = "file"

    def __init__(
        self,
        path: str,
        *,
        format: Literal["text", "jsonl", "markdown"] = "text",
        required: bool = True,
    ) -> None:
        if not path:
            raise ValueError("file sink requires 'path'")
        self.path = validate_file_sink_path(path)
        self.format = format
        self.required = required
        self.path.parent.mkdir(parents=True, exist_ok=True)

    async def send(self, ctx: SendContext) -> None:
        if self.format == "jsonl":
            await asyncio.to_thread(self._write_jsonl, ctx)
        elif self.format == "markdown":
            await asyncio.to_thread(self._write_markdown, ctx)
        else:
            await asyncio.to_thread(self._write_text, ctx)
        logger.debug("file_written", feed=ctx.feed, path=str(self.path))

    def _write_jsonl(self, ctx: SendContext) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            for item in ctx.items:
                row = {
                    "feed": ctx.feed,
                    "title": item.title,
                    "url": item.canonical_url,
                    "summary": item.llm_summary or item.summary,
                    "source_type": item.source_type,
                    "source_name": item.source_name,
                    "published_at": item.published_at.isoformat() if item.published_at else None,
                    "relevance": item.relevance,
                    "structured": item.structured,
                }
                f.write(json.dumps(row, ensure_ascii=False))
                f.write("\n")

    def _write_text(self, ctx: SendContext) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            for msg in ctx.messages:
                f.write(msg)
                f.write("\n\n---\n\n")

    def _write_markdown(self, ctx: SendContext) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            if ctx.intro:
                f.write(f"## {ctx.intro}\n\n")
            for item in ctx.items:
                title = item.title or "(untitled)"
                f.write(f"### {title}\n\n")
                summary = item.llm_summary or item.summary
                if summary:
                    f.write(f"{summary}\n\n")
                url = safe_url(item.canonical_url)
                if url:
                    f.write(f"[link]({url})  \n")
                if item.source_name:
                    f.write(f"_{item.source_name}_\n\n")
            f.write("\n---\n\n")

    async def aclose(self) -> None:
        pass
