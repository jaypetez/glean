"""Tests for e2e-only API reset helpers."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from glean.api.app import make_app
from glean.state.store import StateStore

pytestmark = pytest.mark.asyncio


async def test_test_reset_route_is_not_registered_outside_test_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GLEAN_ENABLE_DOCS", "1")
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


async def test_test_reset_clears_rate_limit_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GLEAN_TEST_MODE", "1")
    state = StateStore(tmp_path / "state.db")
    await state.open()
    try:
        app = make_app(state, tmp_path / "state.db")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            limited_statuses = [
                (await client.get("/api/v1/initialize")).status_code for _ in range(11)
            ]
            reset = await client.post(
                "/api/v1/test/reset",
                headers={"X-Glean-Api-Key": app.state.glean_api_key},
            )
            after_reset = await client.get("/api/v1/initialize")
    finally:
        await state.close()

    assert 429 in limited_statuses
    assert reset.status_code == 200
    assert after_reset.status_code == 200


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
            feed_runs = await state.db.execute_fetchall(
                "SELECT feed, bootstrapped FROM feed_runs ORDER BY feed"
            )
            digests = await state.db.execute_fetchall(
                "SELECT feed_name FROM digests ORDER BY sent_at DESC, id DESC"
            )
            run_history = await state.db.execute_fetchall(
                "SELECT feed_name, status FROM feed_run_history ORDER BY started_at DESC, id DESC"
            )
    finally:
        await state.close()

    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "message": "test state reset"}
    assert active_config.read_text(encoding="utf-8") == fixture_config.read_text(encoding="utf-8")
    assert feed_runs == [("fixture-feed", 1)]
    assert digests == [("fixture-feed",), ("fixture-feed",), ("fixture-feed",)]
    assert run_history == [
        ("fixture-feed", "success"),
        ("fixture-feed", "success"),
        ("fixture-feed", "skip"),
        ("fixture-feed", "failure"),
        ("fixture-feed", "success"),
    ]


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


async def test_test_reset_seeds_primary_and_secondary_fixture_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture_config = tmp_path / "fixture-feeds.yaml"
    active_config = tmp_path / "active-feeds.yaml"
    fixture_config.write_text(
        """
feeds:
  - name: alpha
    schedule: every 1h
    chat_id: \"12345\"
    sources:
      - type: rss
        url: https://example.com/alpha.xml
    pipeline:
      - dedup
  - name: beta
    schedule: daily 09:00
    chat_id: \"67890\"
    sources:
      - type: rss
        url: https://example.com/beta.xml
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
    try:
        app = make_app(state, tmp_path / "state.db")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/test/reset",
                headers={"X-Glean-Api-Key": app.state.glean_api_key},
            )
            feed_runs = await state.db.execute_fetchall(
                "SELECT feed, last_error, alert_active, bootstrapped FROM feed_runs ORDER BY feed"
            )
            digests = await state.db.execute_fetchall(
                "SELECT feed_name, intro FROM digests ORDER BY sent_at DESC, id DESC"
            )
            run_history = await state.db.execute_fetchall(
                "SELECT feed_name, status, sent, error FROM feed_run_history "
                "ORDER BY started_at DESC, id DESC"
            )
    finally:
        await state.close()

    assert resp.status_code == 200
    assert feed_runs == [
        ("alpha", None, 0, 1),
        ("beta", "ConnectionError: timeout", 1, 1),
    ]
    assert digests == [
        ("alpha", "Primary digest 1"),
        ("alpha", "Primary digest 2"),
        ("alpha", "Primary digest 3"),
        ("beta", "Secondary digest"),
    ]
    assert run_history == [
        ("alpha", "success", 3, None),
        ("alpha", "success", 2, None),
        ("alpha", "skip", 0, None),
        ("alpha", "failure", 0, "ConnectionError: timeout"),
        ("alpha", "success", 1, None),
    ]


async def test_test_seed_digest_route_is_not_registered_outside_test_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GLEAN_ENABLE_DOCS", "1")
    state = StateStore(tmp_path / "state.db")
    await state.open()
    try:
        app = make_app(state, tmp_path / "state.db")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/test/seed-digest",
                headers={"X-Glean-Api-Key": app.state.glean_api_key},
                json={"feed_name": "alpha", "body": "hello"},
            )
            openapi = await client.get("/api/openapi.json")
    finally:
        await state.close()

    assert resp.status_code == 404
    assert "/api/v1/test/seed-digest" not in openapi.json()["paths"]


async def test_test_seed_digest_inserts_digest_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GLEAN_TEST_MODE", "1")
    state = StateStore(tmp_path / "state.db")
    await state.open()
    try:
        app = make_app(state, tmp_path / "state.db")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/test/seed-digest",
                headers={"X-Glean-Api-Key": app.state.glean_api_key},
                json={
                    "feed_name": "alpha",
                    "style": "html",
                    "intro": "Digest intro",
                    "body": "<p>hello</p>",
                    "item_count": 2,
                    "trace_id": "trace-123",
                },
            )
            rows = await state.db.execute_fetchall(
                "SELECT feed_name, style, intro, body, item_count, trace_id FROM digests"
            )
    finally:
        await state.close()

    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert rows == [("alpha", "html", "Digest intro", "<p>hello</p>", 2, "trace-123")]


async def test_test_reset_clears_seeded_digests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GLEAN_TEST_MODE", "1")
    state = StateStore(tmp_path / "state.db")
    await state.open()
    try:
        app = make_app(state, tmp_path / "state.db")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            seed = await client.post(
                "/api/v1/test/seed-digest",
                headers={"X-Glean-Api-Key": app.state.glean_api_key},
                json={"feed_name": "alpha", "body": "hello"},
            )
            before_reset = await state.db.execute_fetchall("SELECT id FROM digests")
            reset = await client.post(
                "/api/v1/test/reset",
                headers={"X-Glean-Api-Key": app.state.glean_api_key},
            )
            after_reset = await state.db.execute_fetchall("SELECT id FROM digests")
    finally:
        await state.close()

    assert seed.status_code == 200
    assert before_reset != []
    assert reset.status_code == 200
    assert after_reset == []


async def test_test_seed_digest_route_is_exempt_from_rate_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GLEAN_TEST_MODE", "1")
    state = StateStore(tmp_path / "state.db")
    await state.open()
    try:
        app = make_app(state, tmp_path / "state.db")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            statuses = []
            for index in range(65):
                response = await client.post(
                    "/api/v1/test/seed-digest",
                    headers={"X-Glean-Api-Key": app.state.glean_api_key},
                    json={"feed_name": "alpha", "body": f"hello {index}"},
                )
                statuses.append(response.status_code)
    finally:
        await state.close()

    assert statuses == [200] * 65


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
