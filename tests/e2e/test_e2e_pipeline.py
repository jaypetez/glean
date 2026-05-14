"""End-to-end smoke test: glean fetches mock RSS, calls mock Ollama, posts to mock Telegram."""
from __future__ import annotations

import time

import httpx
import pytest

from tests.e2e.urls import OLLAMA_URL, TELEGRAM_URL

pytestmark = pytest.mark.e2e


def _wait_for_messages(
    url: str,
    min_count: int = 1,
    timeout: float = 60.0,
    chat_id: str | None = None,
) -> list[dict]:
    """Poll the mock-telegram messages endpoint until at least min_count arrive."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            msgs = httpx.get(url, timeout=5.0).json()
            if chat_id is not None:
                msgs = [m for m in msgs if str(m.get("chat", {}).get("id")) == chat_id]
            if len(msgs) >= min_count:
                return msgs
        except Exception:  # noqa: BLE001
            pass
        time.sleep(2)
    return []


def test_glean_sends_digest_to_telegram(e2e_stack: None) -> None:
    """After the e2e stack is up, glean should send at least one digest to mock-telegram."""
    # Schedule is "every 10s" + bootstrap: send-all → first tick should fire ~immediately
    msgs = _wait_for_messages(
        f"{TELEGRAM_URL}/__messages",
        min_count=1,
        timeout=60,
        chat_id="1234",
    )

    assert len(msgs) > 0, "mock-telegram never received any messages from glean"

    # The first message should be a digest containing our intro and at least one mock article
    first = msgs[0]
    text = first.get("text", "")
    assert "E2E test digest" in text or "Mock article" in text, (
        f"unexpected message text: {text[:200]}"
    )


def test_glean_calls_mock_ollama_for_summarization(e2e_stack: None) -> None:
    """The pipeline includes a summarize stage, so mock-ollama should receive chat calls."""
    # Ensure glean has had time to tick
    _wait_for_messages(f"{TELEGRAM_URL}/__messages", min_count=1, timeout=60)

    calls = httpx.get(f"{OLLAMA_URL}/__calls", timeout=5).json()
    assert len(calls) > 0, "mock-ollama received no LLM calls"

    # Each call should have a model name and messages list
    first = calls[0]
    assert first.get("model")
    assert isinstance(first.get("messages"), list)
