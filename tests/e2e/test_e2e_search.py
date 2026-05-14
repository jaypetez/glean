"""E2E test: glean fetches mock SearXNG, calls mock Ollama, sends to mock Telegram."""
from __future__ import annotations

import time

import httpx
import pytest

from tests.e2e.urls import SEARXNG_URL, TELEGRAM_URL

pytestmark = pytest.mark.e2e


def _wait_for_search_messages(timeout: float = 60.0) -> list[dict]:
    """Poll mock-telegram for messages tagged with the search-feed chat_id."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            msgs = httpx.get(f"{TELEGRAM_URL}/__messages", timeout=5.0).json()
            # search feed sends to chat_id=5678; rss feed sends to chat_id=1234
            search_msgs = [m for m in msgs if str(m.get("chat", {}).get("id")) == "5678"]
            if search_msgs:
                return search_msgs
        except Exception:  # noqa: BLE001
            pass
        time.sleep(2)
    return []


def test_search_feed_sends_digest(e2e_stack: None) -> None:
    """The e2e-search-feed should deliver a search-driven digest to mock-telegram."""
    msgs = _wait_for_search_messages(timeout=60)
    assert len(msgs) > 0, "mock-telegram never received a search digest (chat_id=5678)"
    text = msgs[0].get("text", "")
    # Either the intro line or one of the mock result titles should appear
    assert "E2E search digest" in text or "Mock Search Result" in text, (
        f"unexpected message text: {text[:200]}"
    )


def test_search_feed_queries_mock_searxng(e2e_stack: None) -> None:
    """mock-searxng should record the query glean sent."""
    _wait_for_search_messages(timeout=60)
    queries = httpx.get(f"{SEARXNG_URL}/__queries", timeout=5).json()
    assert len(queries) > 0, "mock-searxng received no queries"
    # All queries should have format=json (glean asks for JSON specifically)
    assert all(q["format"] == "json" for q in queries)
    # Our test query should appear in at least one of the recorded queries
    assert any(q["q"] == "mock test query" for q in queries), (
        f"expected query 'mock test query', got: {[q['q'] for q in queries]}"
    )
