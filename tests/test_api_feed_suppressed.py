from __future__ import annotations

import textwrap
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from glean.api.app import make_app
from glean.state.store import StateStore

pytestmark = pytest.mark.asyncio

_SAMPLE_YAML = textwrap.dedent(
    """
    defaults:
      llm: {provider: openai, model: gpt-4o-mini}
    feeds:
      - name: alpha
        schedule: "every 1h"
        chat_id: -1
        sources:
          - type: rss
            url: https://example.com/alpha.xml
        pipeline:
          - dedup
      - name: beta
        schedule: "every 2h"
        chat_id: -2
        sources:
          - type: rss
            url: https://example.com/beta.xml
        pipeline:
          - dedup
    """
)


@pytest.fixture
async def configured_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cfg_path = tmp_path / "feeds.yaml"
    cfg_path.write_text(_SAMPLE_YAML, encoding="utf-8")
    monkeypatch.setenv("GLEAN_CONFIG", str(cfg_path))
    state = StateStore(tmp_path / "state.db")
    await state.open()
    app = make_app(state, tmp_path / "state.db")
    yield app, state
    await state.close()


@pytest.fixture
async def client(configured_app):
    app, _ = configured_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
def auth_headers(configured_app) -> dict[str, str]:
    app, _ = configured_app
    return {"X-Glean-Api-Key": app.state.glean_api_key}


async def _ensure_suppressed_table(state: StateStore) -> None:
    await state.db.execute(
        """
        CREATE TABLE IF NOT EXISTS semantic_dedup_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            feed_name TEXT NOT NULL,
            suppressed_at TEXT NOT NULL,
            suppressed_url TEXT NOT NULL,
            suppressed_title TEXT,
            matched_url TEXT NOT NULL,
            matched_title TEXT,
            similarity REAL NOT NULL,
            trace_id TEXT
        )
        """
    )
    await state.db.commit()


async def _insert_suppressed(
    state: StateStore,
    *,
    feed_name: str,
    suppressed_at: datetime,
    suppressed_url: str,
    suppressed_title: str | None = None,
    matched_url: str,
    matched_title: str | None = None,
    similarity: float = 0.9,
    trace_id: str | None = None,
) -> int:
    await _ensure_suppressed_table(state)
    cursor = await state.db.execute(
        """
        INSERT INTO semantic_dedup_log (
            feed_name,
            suppressed_at,
            suppressed_url,
            suppressed_title,
            matched_url,
            matched_title,
            similarity,
            trace_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            feed_name,
            suppressed_at.isoformat(),
            suppressed_url,
            suppressed_title,
            matched_url,
            matched_title,
            similarity,
            trace_id,
        ),
    )
    await state.db.commit()
    row_id = cursor.lastrowid
    assert row_id is not None
    return int(row_id)


async def test_list_feed_suppressed_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/feeds/alpha/suppressed")

    assert resp.status_code == 401


async def test_list_feed_suppressed_returns_rows(
    client: AsyncClient,
    auth_headers: dict[str, str],
    configured_app,
) -> None:
    _, state = configured_app
    row_id = await _insert_suppressed(
        state,
        feed_name="alpha",
        suppressed_at=datetime(2025, 1, 1, tzinfo=UTC),
        suppressed_url="https://example.com/new",
        suppressed_title="New title",
        matched_url="https://example.com/old",
        matched_title="Old title",
        similarity=0.97,
        trace_id="trace-123",
    )

    resp = await client.get("/api/v1/feeds/alpha/suppressed", headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert [item["id"] for item in body] == [row_id]
    assert body[0]["feed_name"] == "alpha"
    assert body[0]["suppressed_at"] == "2025-01-01T00:00:00Z"
    assert body[0]["suppressed_url"] == "https://example.com/new"
    assert body[0]["suppressed_title"] == "New title"
    assert body[0]["matched_url"] == "https://example.com/old"
    assert body[0]["matched_title"] == "Old title"
    assert body[0]["similarity"] == pytest.approx(0.97)
    assert body[0]["trace_id"] == "trace-123"


async def test_list_feed_suppressed_paginates_without_overlap(
    client: AsyncClient,
    auth_headers: dict[str, str],
    configured_app,
) -> None:
    _, state = configured_app
    base = datetime(2025, 1, 1, tzinfo=UTC)
    inserted_ids: list[int] = []
    for index in range(5):
        inserted_ids.append(
            await _insert_suppressed(
                state,
                feed_name="alpha",
                suppressed_at=base + timedelta(minutes=index),
                suppressed_url=f"https://example.com/new-{index}",
                matched_url=f"https://example.com/old-{index}",
            )
        )
    await _insert_suppressed(
        state,
        feed_name="beta",
        suppressed_at=base + timedelta(minutes=10),
        suppressed_url="https://example.com/beta-new",
        matched_url="https://example.com/beta-old",
    )

    first = await client.get("/api/v1/feeds/alpha/suppressed?limit=2", headers=auth_headers)

    assert first.status_code == 200
    first_ids = [item["id"] for item in first.json()]
    assert len(first_ids) == 2

    second = await client.get(
        f"/api/v1/feeds/alpha/suppressed?limit=2&before={first_ids[-1]}",
        headers=auth_headers,
    )

    assert second.status_code == 200
    second_ids = [item["id"] for item in second.json()]
    assert len(second_ids) == 2
    assert set(first_ids).isdisjoint(second_ids)
    assert first_ids + second_ids == sorted(inserted_ids, reverse=True)[:4]


async def test_list_feed_suppressed_empty_result(
    client: AsyncClient,
    auth_headers: dict[str, str],
    configured_app,
) -> None:
    _, state = configured_app
    await _ensure_suppressed_table(state)

    resp = await client.get("/api/v1/feeds/alpha/suppressed", headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_feed_suppressed_unknown_feed_returns_404(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    resp = await client.get("/api/v1/feeds/nonexistent/suppressed", headers=auth_headers)

    assert resp.status_code == 404


@pytest.mark.parametrize("limit", [0, 201])
async def test_list_feed_suppressed_rejects_invalid_limit(
    client: AsyncClient,
    auth_headers: dict[str, str],
    limit: int,
) -> None:
    resp = await client.get(
        f"/api/v1/feeds/alpha/suppressed?limit={limit}",
        headers=auth_headers,
    )

    assert resp.status_code == 422
