from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from glean.api.app import make_app
from glean.state.store import StateStore

pytestmark = pytest.mark.asyncio


async def _get_status(tmp_path: Path, path: str) -> int:
    db_path = tmp_path / f"{path.replace('/', '_')}.db"
    state = StateStore(db_path)
    await state.open()
    try:
        app = make_app(state, db_path)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(path)
            return resp.status_code
    finally:
        await state.close()


async def test_swagger_docs_are_disabled_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GLEAN_ENABLE_DOCS", raising=False)

    docs_status = await _get_status(tmp_path, "/api/docs")
    openapi_status = await _get_status(tmp_path, "/api/openapi.json")

    assert docs_status == 404
    assert openapi_status == 404


async def test_swagger_docs_can_be_enabled_with_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GLEAN_ENABLE_DOCS", "1")

    docs_status = await _get_status(tmp_path, "/api/docs")
    openapi_status = await _get_status(tmp_path, "/api/openapi.json")

    assert docs_status == 200
    assert openapi_status == 200
