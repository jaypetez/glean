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


async def _ensure_digests_table(state: StateStore) -> None:
    await state.db.execute(
        """
        CREATE TABLE IF NOT EXISTS digests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            feed_name TEXT NOT NULL,
            sent_at TEXT NOT NULL,
            style TEXT NOT NULL,
            intro TEXT,
            body TEXT NOT NULL,
            fragment_index INTEGER NOT NULL,
            item_count INTEGER NOT NULL,
            trace_id TEXT
        )
        """
    )
    await state.db.commit()


async def _insert_digest(
    state: StateStore,
    *,
    feed_name: str,
    sent_at: datetime,
    style: str = "html",
    intro: str | None = None,
    body: str = "digest body",
    fragment_index: int = 0,
    item_count: int = 1,
    trace_id: str | None = None,
) -> int:
    await _ensure_digests_table(state)
    cursor = await state.db.execute(
        """
        INSERT INTO digests (
            feed_name,
            sent_at,
            style,
            intro,
            body,
            fragment_index,
            item_count,
            trace_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            feed_name,
            sent_at.isoformat(),
            style,
            intro,
            body,
            fragment_index,
            item_count,
            trace_id,
        ),
    )
    await state.db.commit()
    return int(cursor.lastrowid)


async def test_list_digests_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/digests")

    assert resp.status_code == 401


async def test_list_digests_returns_rows(
    client: AsyncClient,
    auth_headers: dict[str, str],
    configured_app,
) -> None:
    _, state = configured_app
    digest_id = await _insert_digest(
        state,
        feed_name="alpha",
        sent_at=datetime(2025, 1, 1, tzinfo=UTC),
        intro="top stories",
        body="hello world",
        fragment_index=2,
        item_count=3,
        trace_id="trace-123",
    )

    resp = await client.get("/api/v1/digests", headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert [item["id"] for item in body] == [digest_id]
    assert body[0]["feed_name"] == "alpha"
    assert body[0]["style"] == "html"
    assert body[0]["intro"] == "top stories"
    assert body[0]["body"] == "hello world"
    assert body[0]["fragment_index"] == 2
    assert body[0]["item_count"] == 3
    assert body[0]["trace_id"] == "trace-123"


async def test_feed_digests_empty_result(
    client: AsyncClient,
    auth_headers: dict[str, str],
    configured_app,
) -> None:
    _, state = configured_app
    await _ensure_digests_table(state)

    resp = await client.get("/api/v1/feeds/beta/digests", headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_digests_paginates_without_overlap(
    client: AsyncClient,
    auth_headers: dict[str, str],
    configured_app,
) -> None:
    _, state = configured_app
    base = datetime(2025, 1, 1, tzinfo=UTC)
    inserted_ids: list[int] = []
    for index in range(10):
        inserted_ids.append(
            await _insert_digest(
                state,
                feed_name="alpha" if index % 2 == 0 else "beta",
                sent_at=base + timedelta(minutes=index),
                body=f"digest {index}",
            )
        )

    first = await client.get("/api/v1/digests?limit=5", headers=auth_headers)

    assert first.status_code == 200
    first_ids = [item["id"] for item in first.json()]
    assert len(first_ids) == 5

    second = await client.get(
        f"/api/v1/digests?limit=5&before={first_ids[-1]}",
        headers=auth_headers,
    )

    assert second.status_code == 200
    second_ids = [item["id"] for item in second.json()]
    assert len(second_ids) == 5
    assert set(first_ids).isdisjoint(second_ids)
    assert first_ids + second_ids == sorted(inserted_ids, reverse=True)


async def test_list_digests_paginates_without_overlap_when_sent_at_is_not_monotonic(
    client: AsyncClient,
    auth_headers: dict[str, str],
    configured_app,
) -> None:
    _, state = configured_app
    base = datetime(2025, 1, 1, tzinfo=UTC)
    newest_id = await _insert_digest(
        state,
        feed_name="alpha",
        sent_at=base + timedelta(minutes=3),
        body="newest",
    )
    older_cursor_id = await _insert_digest(
        state,
        feed_name="alpha",
        sent_at=base + timedelta(minutes=1),
        body="cursor",
    )
    middle_id = await _insert_digest(
        state,
        feed_name="beta",
        sent_at=base + timedelta(minutes=2),
        body="middle",
    )
    oldest_id = await _insert_digest(
        state,
        feed_name="beta",
        sent_at=base,
        body="oldest",
    )

    first = await client.get("/api/v1/digests?limit=2", headers=auth_headers)

    assert first.status_code == 200
    assert [item["id"] for item in first.json()] == [newest_id, middle_id]

    second = await client.get(
        f"/api/v1/digests?limit=2&before={middle_id}",
        headers=auth_headers,
    )

    assert second.status_code == 200
    assert [item["id"] for item in second.json()] == [older_cursor_id, oldest_id]


async def test_feed_digests_unknown_feed_returns_404(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    resp = await client.get("/api/v1/feeds/nonexistent/digests", headers=auth_headers)

    assert resp.status_code == 404


@pytest.mark.parametrize("limit", [0, 201])
async def test_list_digests_rejects_invalid_limit(
    client: AsyncClient,
    auth_headers: dict[str, str],
    limit: int,
) -> None:
    resp = await client.get(f"/api/v1/digests?limit={limit}", headers=auth_headers)

    assert resp.status_code == 422


async def test_list_digests_rejects_negative_before(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    resp = await client.get("/api/v1/digests?before=-1", headers=auth_headers)

    assert resp.status_code == 422
