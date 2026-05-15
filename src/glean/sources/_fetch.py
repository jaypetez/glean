from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

import httpx

from glean.security.ssrf import validate_url

DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 MiB
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}


class ResponseTooLargeError(ValueError):
    pass


async def limited_get(
    client: httpx.AsyncClient,
    url: str,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    headers: dict[str, str] | None = None,
    follow_redirects: bool = False,
    **kwargs: Any,
) -> httpx.Response:
    """GET with hard cap on response body size, streaming to abort early."""
    async with client.stream(
        "GET",
        url,
        headers=headers,
        follow_redirects=follow_redirects,
        **kwargs,
    ) as resp:
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


async def follow_with_validation(
    client: httpx.AsyncClient,
    url: str,
    *,
    max_hops: int = 5,
    allow_private: bool = False,
    max_bytes: int = DEFAULT_MAX_BYTES,
    headers: dict[str, str] | None = None,
    **kwargs: Any,
) -> httpx.Response:
    """Follow redirects with per-hop SSRF validation and response-size caps.

    The caller must use a client transport whose allow-private policy matches
    ``allow_private``; otherwise the transport can reject URLs allowed here.
    """
    current_url = validate_url(url, allow_private=allow_private)
    request_kwargs = {
        **kwargs,
        "headers": headers,
        "max_bytes": max_bytes,
        "follow_redirects": False,
    }

    for hop in range(max_hops + 1):
        resp = await limited_get(client, current_url, **request_kwargs)
        if resp.status_code not in _REDIRECT_STATUSES:
            return resp
        location = resp.headers.get("Location")
        if not location:
            return resp
        if hop == max_hops:
            break
        current_url = validate_url(urljoin(str(resp.url), location), allow_private=allow_private)

    raise httpx.TooManyRedirects(f"Exceeded maximum redirects ({max_hops})", request=resp.request)


def _parse_content_length(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
