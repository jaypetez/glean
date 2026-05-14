"""Tests for the FastAPI foundation + auth."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from glean.api.app import make_app
from glean.state.store import StateStore

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def app_and_state(tmp_path: Path):
    state = StateStore(tmp_path / "state.db")
    await state.open()
    app = make_app(state, tmp_path / "state.db")
    yield app, state
    await state.close()


@pytest.fixture
async def client(app_and_state):
    app, _ = app_and_state
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
def api_key(app_and_state) -> str:
    app, _ = app_and_state
    return app.state.glean_api_key


async def test_healthz_unauthenticated(client: AsyncClient) -> None:
    """/healthz must work without auth (Docker HEALTHCHECK depends on this)."""
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_healthz_reports_generic_db_error(tmp_path: Path) -> None:
    """/healthz must not expose exception details to callers."""

    class BrokenDb:
        def execute(self, _query: str):
            raise RuntimeError("sensitive database path")

    app = make_app(SimpleNamespace(db=BrokenDb()), tmp_path / "state.db")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/healthz")

    assert resp.status_code == 503
    assert resp.json() == {"detail": "db error"}


async def test_initialize_returns_api_key(client: AsyncClient, api_key: str) -> None:
    """/api/v1/initialize is unauthenticated and returns the api_key."""
    resp = await client.get("/api/v1/initialize")
    assert resp.status_code == 200
    body = resp.json()
    assert body["api_key"] == api_key
    assert body["version"]
    assert body["auth_disabled"] is False


async def test_authenticated_route_rejects_missing_key(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 401


async def test_authenticated_route_rejects_wrong_key(client: AsyncClient) -> None:
    resp = await client.get(
        "/api/v1/health",
        headers={"X-Glean-Api-Key": "obviously-not-the-real-key"},
    )
    assert resp.status_code == 401


async def test_authenticated_route_accepts_valid_key(
    client: AsyncClient, api_key: str
) -> None:
    resp = await client.get(
        "/api/v1/health",
        headers={"X-Glean-Api-Key": api_key},
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_auth_disabled_via_env(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GLEAN_DISABLE_AUTH", "1")
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200


async def test_api_key_persisted_across_calls(tmp_path: Path) -> None:
    """get_or_create_api_key should return the same key on subsequent calls."""
    from glean.api.auth import get_or_create_api_key

    db_path = tmp_path / "state.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    key1 = get_or_create_api_key(db_path)
    key2 = get_or_create_api_key(db_path)
    assert key1 == key2
    assert len(key1) >= 32


async def test_api_key_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from glean.api.auth import get_or_create_api_key

    monkeypatch.setenv("GLEAN_API_KEY", "env-override-key")
    assert get_or_create_api_key(tmp_path / "x.db") == "env-override-key"


async def test_openapi_schema_available(client: AsyncClient) -> None:
    resp = await client.get("/api/openapi.json")
    assert resp.status_code == 200
    body = resp.json()
    assert body["info"]["title"] == "glean"
