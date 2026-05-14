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


async def test_api_key_persisted_as_verifier_not_cleartext(tmp_path: Path) -> None:
    """Restarted apps should verify the key without storing or re-revealing it."""
    state1 = StateStore(tmp_path / "state.db")
    await state1.open()
    app1 = make_app(state1, tmp_path / "state.db")
    api_key = app1.state.glean_api_key
    await state1.close()

    assert isinstance(api_key, str)
    assert len(api_key) >= 32
    assert (tmp_path / "api_key").read_text(encoding="utf-8").strip() != api_key

    state2 = StateStore(tmp_path / "state.db")
    await state2.open()
    app2 = make_app(state2, tmp_path / "state.db")
    assert app2.state.glean_api_key is None
    assert app2.state.glean_api_key_material.plaintext is None
    async with AsyncClient(transport=ASGITransport(app=app2), base_url="http://test") as ac:
        init = await ac.get("/api/v1/initialize")
        health = await ac.get("/api/v1/health", headers={"X-Glean-Api-Key": api_key})
        init_after_auth = await ac.get("/api/v1/initialize")
    await state2.close()

    assert init.status_code == 200
    assert init.json()["api_key"] is None
    assert health.status_code == 200
    assert app2.state.glean_api_key_material.plaintext == api_key
    assert init_after_auth.json()["api_key"] is None


async def test_legacy_plaintext_api_key_file_is_migrated(tmp_path: Path) -> None:
    legacy_key = "legacy-manual-key"
    (tmp_path / "api_key").write_text(legacy_key, encoding="utf-8")

    state = StateStore(tmp_path / "state.db")
    await state.open()
    app = make_app(state, tmp_path / "state.db")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        init = await ac.get("/api/v1/initialize")
        health = await ac.get("/api/v1/health", headers={"X-Glean-Api-Key": legacy_key})
    await state.close()

    persisted = (tmp_path / "api_key").read_text(encoding="utf-8").strip()
    assert persisted != legacy_key
    assert persisted.startswith("pbkdf2_sha256$")
    assert init.json()["api_key"] == legacy_key
    assert health.status_code == 200


async def test_api_key_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from glean.api.auth import get_or_create_api_key

    monkeypatch.setenv("GLEAN_API_KEY", "env-override-key")
    assert get_or_create_api_key(tmp_path / "x.db").plaintext == "env-override-key"


async def test_openapi_schema_available(client: AsyncClient) -> None:
    resp = await client.get("/api/openapi.json")
    assert resp.status_code == 200
    body = resp.json()
    assert body["info"]["title"] == "glean"


async def test_spa_not_mounted_when_dist_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If no dist dir is available, /api and /healthz still work; / 404s gracefully."""
    monkeypatch.setenv("GLEAN_UI_DIST", str(tmp_path / "nonexistent"))
    state = StateStore(tmp_path / "state.db")
    await state.open()
    try:
        app = make_app(state, tmp_path / "state.db")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            healthz = await ac.get("/healthz")
            assert healthz.status_code == 200
            root = await ac.get("/")
            assert root.status_code == 404
    finally:
        await state.close()


async def test_spa_mounted_when_dist_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If a dist directory with index.html exists, / serves the SPA shell."""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html><body>glean ui</body></html>")
    monkeypatch.setenv("GLEAN_UI_DIST", str(dist))
    state = StateStore(tmp_path / "state.db")
    await state.open()
    try:
        app = make_app(state, tmp_path / "state.db")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            root = await ac.get("/")
            assert root.status_code == 200
            assert b"glean ui" in root.content
            healthz = await ac.get("/healthz")
            assert healthz.status_code == 200
    finally:
        await state.close()
