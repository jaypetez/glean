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


async def _insert_run(
    state: StateStore,
    *,
    feed_name: str,
    started_at: datetime,
    duration_ms: int = 1,
    status: str = "success",
    fetched: int = 0,
    after_dedup: int = 0,
    dropped: int = 0,
    sent: int = 0,
    overflow: int = 0,
    error: str | None = None,
    trace_id: str | None = None,
    dry_run: bool = False,
) -> int:
    cursor = await state.db.execute(
        """
        INSERT INTO feed_run_history (
            feed_name,
            started_at,
            duration_ms,
            status,
            fetched,
            after_dedup,
            dropped,
            sent,
            overflow,
            error,
            trace_id,
            dry_run
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            feed_name,
            started_at.isoformat(),
            duration_ms,
            status,
            fetched,
            after_dedup,
            dropped,
            sent,
            overflow,
            error,
            trace_id,
            1 if dry_run else 0,
        ),
    )
    await state.db.commit()
    row_id = cursor.lastrowid
    assert row_id is not None
    return int(row_id)


async def test_list_feed_runs_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/feeds/alpha/runs")

    assert resp.status_code == 401


async def test_list_feed_runs_paginates_without_overlap(
    client: AsyncClient,
    auth_headers: dict[str, str],
    configured_app,
) -> None:
    _, state = configured_app
    base = datetime(2025, 1, 1, tzinfo=UTC)
    inserted_ids: list[int] = []
    for index in range(5):
        inserted_ids.append(
            await _insert_run(
                state,
                feed_name="alpha",
                started_at=base + timedelta(minutes=index),
                duration_ms=index,
            )
        )
    await _insert_run(state, feed_name="beta", started_at=base + timedelta(minutes=10))

    first = await client.get("/api/v1/feeds/alpha/runs?limit=2", headers=auth_headers)

    assert first.status_code == 200
    first_ids = [item["id"] for item in first.json()]
    assert len(first_ids) == 2

    second = await client.get(
        f"/api/v1/feeds/alpha/runs?limit=2&before={first_ids[-1]}",
        headers=auth_headers,
    )

    assert second.status_code == 200
    second_ids = [item["id"] for item in second.json()]
    assert len(second_ids) == 2
    assert set(first_ids).isdisjoint(second_ids)
    assert first_ids + second_ids == sorted(inserted_ids, reverse=True)[:4]


async def test_list_feed_runs_filters_by_status(
    client: AsyncClient,
    auth_headers: dict[str, str],
    configured_app,
) -> None:
    _, state = configured_app
    base = datetime(2025, 1, 1, tzinfo=UTC)
    await _insert_run(state, feed_name="alpha", started_at=base, status="success")
    failure_id = await _insert_run(
        state,
        feed_name="alpha",
        started_at=base + timedelta(minutes=1),
        status="failure",
        error="boom",
    )
    await _insert_run(
        state,
        feed_name="alpha",
        started_at=base + timedelta(minutes=2),
        status="skip",
    )
    await _insert_run(
        state,
        feed_name="beta",
        started_at=base + timedelta(minutes=3),
        status="failure",
    )

    resp = await client.get("/api/v1/feeds/alpha/runs?status=failure", headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["id"] == failure_id
    assert body[0]["feed_name"] == "alpha"
    assert body[0]["started_at"] == "2025-01-01T00:01:00Z"
    assert body[0]["duration_ms"] == 1
    assert body[0]["status"] == "failure"
    assert body[0]["fetched"] == 0
    assert body[0]["after_dedup"] == 0
    assert body[0]["dropped"] == 0
    assert body[0]["sent"] == 0
    assert body[0]["overflow"] == 0
    assert body[0]["error"] == "boom"
    assert body[0]["trace_id"] is None
    assert body[0]["dry_run"] is False


async def test_list_feed_runs_unknown_feed_returns_404(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    resp = await client.get("/api/v1/feeds/nonexistent/runs", headers=auth_headers)

    assert resp.status_code == 404


@pytest.mark.parametrize("limit", [0, 201])
async def test_list_feed_runs_rejects_invalid_limit(
    client: AsyncClient,
    auth_headers: dict[str, str],
    limit: int,
) -> None:
    resp = await client.get(f"/api/v1/feeds/alpha/runs?limit={limit}", headers=auth_headers)

    assert resp.status_code == 422
