from __future__ import annotations

from pathlib import Path

import pytest

from glean.sources.base import Item
from glean.state.store import StateStore

pytestmark = pytest.mark.asyncio


async def _store(path: Path) -> StateStore:
    s = StateStore(path)
    await s.open()
    return s


def _item(url: str, title: str = "t") -> Item:
    return Item(canonical_url=url, title=title, source_type="rss", source_name="x")


async def test_dedup_first_run_returns_all(tmp_db: Path) -> None:
    s = await _store(tmp_db)
    try:
        items = [_item("a"), _item("b"), _item("c")]
        out = await s.filter_new("ai", items)
        assert {i.canonical_url for i in out} == {"a", "b", "c"}
    finally:
        await s.close()


async def test_mark_seen_then_dedup(tmp_db: Path) -> None:
    s = await _store(tmp_db)
    try:
        items = [_item("a"), _item("b")]
        await s.mark_seen("ai", items, sent=True)
        out = await s.filter_new("ai", [_item("a"), _item("c")])
        assert {i.canonical_url for i in out} == {"c"}
    finally:
        await s.close()


async def test_failure_alert_threshold(tmp_db: Path) -> None:
    s = await _store(tmp_db)
    try:
        count, should = await s.record_failure("ai", "boom", alert_after=3)
        assert (count, should) == (1, False)
        count, should = await s.record_failure("ai", "boom", alert_after=3)
        assert (count, should) == (2, False)
        count, should = await s.record_failure("ai", "boom", alert_after=3)
        assert count == 3 and should is True
        # subsequent failures should not re-alert
        _, should = await s.record_failure("ai", "boom", alert_after=3)
        assert should is False
    finally:
        await s.close()


async def test_recovery_clears_alert(tmp_db: Path) -> None:
    s = await _store(tmp_db)
    try:
        for _ in range(3):
            await s.record_failure("ai", "boom", alert_after=3)
        recovered = await s.record_success("ai")
        assert recovered is True
        # next success should not be flagged as recovery again
        recovered = await s.record_success("ai")
        assert recovered is False
    finally:
        await s.close()


async def test_bootstrap_flag(tmp_db: Path) -> None:
    s = await _store(tmp_db)
    try:
        assert await s.is_bootstrapped("ai") is False
        await s.set_bootstrapped("ai")
        assert await s.is_bootstrapped("ai") is True
    finally:
        await s.close()
