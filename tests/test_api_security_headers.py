from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from glean.api.app import make_app, run_api_server
from glean.state.store import StateStore

pytestmark = pytest.mark.asyncio


EXPECTED_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), camera=(), microphone=()",
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    ),
}


async def test_healthz_returns_security_headers_without_server_header(tmp_path: Path) -> None:
    state = StateStore(tmp_path / "state.db")
    await state.open()
    try:
        app = make_app(state, tmp_path / "state.db")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/healthz")
    finally:
        await state.close()

    assert resp.status_code == 200
    for header, expected in EXPECTED_SECURITY_HEADERS.items():
        assert resp.headers[header] == expected
    assert "Server" not in resp.headers


async def test_run_api_server_disables_identifying_uvicorn_headers(tmp_path: Path) -> None:
    state = StateStore(tmp_path / "state.db")
    await state.open()
    try:
        server = await run_api_server(
            state,
            tmp_path / "state.db",
            host="127.0.0.1",
            port=0,
        )
    finally:
        await state.close()

    assert server.config.server_header is False
    assert server.config.date_header is False
    assert server.config.limit_concurrency == 50
    assert server.config.h11_max_incomplete_event_size == 65_536
