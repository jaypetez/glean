"""Tests for e2e-only API reset helpers."""
from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from glean.api.app import make_app
from glean.state.store import StateStore

pytestmark = pytest.mark.asyncio


async def test_test_reset_route_is_not_registered_outside_test_mode(tmp_path: Path) -> None:
    state = StateStore(tmp_path / "state.db")
    await state.open()
    try:
        app = make_app(state, tmp_path / "state.db")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/test/reset",
                headers={"X-Glean-Api-Key": app.state.glean_api_key},
            )
            openapi = await client.get("/api/openapi.json")
    finally:
        await state.close()

    assert resp.status_code == 404
    assert "/api/v1/test/reset" not in openapi.json()["paths"]
    assert "/api/v1/test/rss" not in openapi.json()["paths"]


async def test_test_reset_restores_fixture_config_and_clears_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture_config = tmp_path / "fixture-feeds.yaml"
    active_config = tmp_path / "active-feeds.yaml"
    fixture_config.write_text(
        """
defaults:
  llm:
    provider: ollama
    model: qwen2.5:7b
feeds:
  - name: fixture-feed
    schedule: every 1h
    chat_id: "12345"
    sources:
      - type: rss
        url: https://example.com/feed.xml
    pipeline:
      - dedup
skills: []
""".strip()
        + "\n",
        encoding="utf-8",
    )
    active_config.write_text("feeds: []\nskills: []\n", encoding="utf-8")
    monkeypatch.setenv("GLEAN_TEST_MODE", "1")
    monkeypatch.setenv("GLEAN_CONFIG", str(active_config))
    monkeypatch.setenv("GLEAN_TEST_CONFIG_FIXTURE", str(fixture_config))

    state = StateStore(tmp_path / "state.db")
    await state.open()
    await state.db.execute(
        "INSERT INTO feed_runs(feed, consecutive_failures, bootstrapped) VALUES (?, 2, 1)",
        ("fixture-feed",),
    )
    await state.db.commit()
    try:
        app = make_app(state, tmp_path / "state.db")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/test/reset",
                headers={"X-Glean-Api-Key": app.state.glean_api_key},
            )
            feed_runs = await state.db.execute_fetchall("SELECT feed FROM feed_runs")
    finally:
        await state.close()

    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "message": "test state reset"}
    assert active_config.read_text(encoding="utf-8") == fixture_config.read_text(encoding="utf-8")
    assert feed_runs == []


async def test_test_reset_can_restore_empty_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    default_config = tmp_path / "default-feeds.yaml"
    empty_config = tmp_path / "empty-feeds.yaml"
    active_config = tmp_path / "active-feeds.yaml"
    default_config.write_text("feeds: []\nskills: []\n", encoding="utf-8")
    empty_config.write_text(
        "defaults:\n  llm:\n    provider: ollama\n    model: qwen2.5:7b\nfeeds: []\nskills: []\n",
        encoding="utf-8",
    )
    active_config.write_text("feeds:\n  - name: stale\n", encoding="utf-8")
    monkeypatch.setenv("GLEAN_TEST_MODE", "1")
    monkeypatch.setenv("GLEAN_CONFIG", str(active_config))
    monkeypatch.setenv("GLEAN_TEST_CONFIG_FIXTURE", str(default_config))
    monkeypatch.setenv("GLEAN_TEST_EMPTY_CONFIG_FIXTURE", str(empty_config))

    state = StateStore(tmp_path / "state.db")
    await state.open()
    try:
        app = make_app(state, tmp_path / "state.db")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/test/reset?fixture=empty",
                headers={"X-Glean-Api-Key": app.state.glean_api_key},
            )
    finally:
        await state.close()

    assert resp.status_code == 200
    assert active_config.read_text(encoding="utf-8") == empty_config.read_text(encoding="utf-8")


async def test_test_rss_route_serves_fixture_feed_in_test_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GLEAN_TEST_MODE", "1")
    state = StateStore(tmp_path / "state.db")
    await state.open()
    try:
        app = make_app(state, tmp_path / "state.db")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/api/v1/test/rss",
                headers={"X-Glean-Api-Key": app.state.glean_api_key},
            )
    finally:
        await state.close()

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/rss+xml")
    assert "glean E2E Feed" in resp.text
