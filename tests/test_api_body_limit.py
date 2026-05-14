from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from glean.api.app import make_app
from glean.state.store import StateStore

pytestmark = pytest.mark.asyncio


async def test_large_content_length_is_rejected_before_route_handling(tmp_path: Path) -> None:
    state = StateStore(tmp_path / "state.db")
    await state.open()
    try:
        app = make_app(state, tmp_path / "state.db")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/config/defaults",
                content=b"x",
                headers={"Content-Length": "2000000"},
            )
    finally:
        await state.close()

    assert resp.status_code == 413
    assert resp.json() == {"detail": "request too large"}


async def test_body_without_content_length_is_metered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GLEAN_MAX_BODY_BYTES", "4")
    state = StateStore(tmp_path / "state.db")
    await state.open()
    try:
        app = make_app(state, tmp_path / "state.db")
        messages = [
            {"type": "http.request", "body": b"123", "more_body": True},
            {"type": "http.request", "body": b"45", "more_body": False},
        ]
        sent: list[dict[str, object]] = []

        async def receive() -> dict[str, object]:
            if messages:
                return messages.pop(0)
            return {"type": "http.disconnect"}

        async def send(message: dict[str, object]) -> None:
            sent.append(message)

        await app(
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": "POST",
                "scheme": "http",
                "path": "/api/v1/config/defaults",
                "raw_path": b"/api/v1/config/defaults",
                "query_string": b"",
                "headers": [(b"host", b"test")],
                "client": ("127.0.0.1", 12345),
                "server": ("test", 80),
            },
            receive,
            send,
        )
    finally:
        await state.close()

    response_start = next(message for message in sent if message["type"] == "http.response.start")
    assert response_start["status"] == 413
