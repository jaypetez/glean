from __future__ import annotations

import httpx

from glean.logging import get_logger

logger = get_logger(__name__)

DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 MiB


class ResponseTooLargeError(ValueError):
    pass


async def limited_get(
    client: httpx.AsyncClient,
    url: str,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    """GET with hard cap on response body size, streaming to abort early."""
    async with client.stream("GET", url, headers=headers, follow_redirects=True) as resp:
        content_length = _parse_content_length(resp.headers.get("content-length"))
        if content_length is not None and content_length > max_bytes:
            raise ResponseTooLargeError(
                f"{url} content-length {content_length} exceeds cap {max_bytes}"
            )

        chunks = bytearray()
        async for chunk in resp.aiter_bytes(chunk_size=65536):
            chunks.extend(chunk)
            if len(chunks) > max_bytes:
                raise ResponseTooLargeError(f"{url} response body exceeded {max_bytes} bytes")

        resp._content = bytes(chunks)
        return resp


def _parse_content_length(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
