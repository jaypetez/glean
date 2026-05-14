from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
import respx

from glean.sources._fetch import DEFAULT_MAX_BYTES, ResponseTooLargeError, limited_get

pytestmark = pytest.mark.asyncio


class _AsyncByteStream(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            yield chunk


@respx.mock
async def test_limited_get_rejects_oversized_streamed_response() -> None:
    respx.get("https://example.com/feed").mock(
        return_value=httpx.Response(200, stream=_AsyncByteStream([b"abc", b"de"]))
    )

    async with httpx.AsyncClient() as client:
        with pytest.raises(ResponseTooLargeError, match="response body exceeded 4 bytes"):
            await limited_get(client, "https://example.com/feed", max_bytes=4)


@respx.mock
async def test_limited_get_rejects_content_length_over_cap_before_streaming() -> None:
    respx.get("https://example.com/feed").mock(
        return_value=httpx.Response(200, headers={"Content-Length": "5"})
    )

    async with httpx.AsyncClient() as client:
        with pytest.raises(ResponseTooLargeError, match="content-length 5 exceeds cap 4"):
            await limited_get(client, "https://example.com/feed", max_bytes=4)


@respx.mock
async def test_limited_get_ignores_bogus_content_length_then_checks_stream() -> None:
    respx.get("https://example.com/feed").mock(
        return_value=httpx.Response(
            200,
            stream=_AsyncByteStream([b"abc", b"de"]),
            headers={"Content-Length": "bogus"},
        )
    )

    async with httpx.AsyncClient() as client:
        with pytest.raises(ResponseTooLargeError, match="response body exceeded 4 bytes"):
            await limited_get(client, "https://example.com/feed", max_bytes=4)


@respx.mock
async def test_limited_get_returns_under_cap_response_with_content_accessible() -> None:
    respx.get("https://example.com/feed").mock(return_value=httpx.Response(200, content=b"hello"))

    async with httpx.AsyncClient() as client:
        resp = await limited_get(client, "https://example.com/feed", max_bytes=5)

    assert resp.status_code == 200
    assert resp.content == b"hello"
    assert resp.text == "hello"


@respx.mock
async def test_limited_get_rejects_two_kibibyte_body_with_one_kibibyte_cap() -> None:
    respx.get("https://example.com/feed").mock(
        return_value=httpx.Response(200, stream=_AsyncByteStream([b"x" * 2048]))
    )

    async with httpx.AsyncClient() as client:
        with pytest.raises(ResponseTooLargeError, match="response body exceeded 1024 bytes"):
            await limited_get(client, "https://example.com/feed", max_bytes=1024)


async def test_default_max_bytes_is_ten_mib() -> None:
    assert DEFAULT_MAX_BYTES == 10 * 1024 * 1024
