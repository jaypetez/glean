from __future__ import annotations

from typing import Any

import httpx
import httpx2

from glean.exceptions import SecurityError
from glean.security.ssrf import validate_url

# Privilege elevation for tightly-scoped internal backends such as SearXNG only.
# Do not use this for arbitrary user-provided URLs.
SSRF_ALLOW_PRIVATE_EXTENSION = "glean_ssrf_allow_private"


class SSRFGuardedTransport(httpx.AsyncHTTPTransport):
    def __init__(self, *args: Any, allow_private: bool = False, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._allow_private = allow_private

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        allow_private = bool(
            request.extensions.get(SSRF_ALLOW_PRIVATE_EXTENSION, self._allow_private)
        )
        try:
            validate_url(str(request.url), allow_private=allow_private)
        except SecurityError as exc:
            raise httpx.RequestError(f"SSRF blocked: {exc}", request=request) from exc
        return await super().handle_async_request(request)


def outbound_timeout(*, read: float = 15.0) -> httpx.Timeout:
    return httpx.Timeout(connect=5.0, read=read, write=5.0, pool=5.0)


# httpx2 twins for SDKs built on httpx2 (anthropic>=1). httpx2 is the maintained
# fork of httpx by its original author; objects crossing the SDK boundary must
# come from httpx2 or the client constructor rejects them.
class SSRFGuardedHttpx2Transport(httpx2.AsyncHTTPTransport):
    def __init__(self, *args: Any, allow_private: bool = False, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._allow_private = allow_private

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        allow_private = bool(
            request.extensions.get(SSRF_ALLOW_PRIVATE_EXTENSION, self._allow_private)
        )
        try:
            validate_url(str(request.url), allow_private=allow_private)
        except SecurityError as exc:
            raise httpx2.RequestError(f"SSRF blocked: {exc}", request=request) from exc
        return await super().handle_async_request(request)


def outbound_timeout_httpx2(*, read: float = 15.0) -> httpx2.Timeout:
    return httpx2.Timeout(connect=5.0, read=read, write=5.0, pool=5.0)
