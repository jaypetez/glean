"""E2E test: glean runs apply_skill with a per-source LLM, ships structured digest."""

from __future__ import annotations

import time

import httpx
import pytest

from tests.e2e.urls import OLLAMA_URL, TELEGRAM_URL

pytestmark = pytest.mark.e2e


def _wait_for_skills_messages(timeout: float = 60.0) -> list[dict]:
    """Poll mock-telegram for messages going to the skills feed (chat_id=9999)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            msgs = httpx.get(f"{TELEGRAM_URL}/__messages", timeout=5.0).json()
            skills_msgs = [m for m in msgs if str(m.get("chat", {}).get("id")) == "9999"]
            if skills_msgs:
                return skills_msgs
        except Exception:  # noqa: BLE001
            pass
        time.sleep(2)
    return []


def test_skills_feed_sends_digest(e2e_stack: None) -> None:
    """The e2e-skills-feed should deliver a digest to mock-telegram."""
    msgs = _wait_for_skills_messages(timeout=60)
    assert len(msgs) > 0, "mock-telegram never received a skills digest (chat_id=9999)"

    text = msgs[0].get("text", "")
    assert "E2E skills digest" in text or "Mock article" in text, (
        f"unexpected message text: {text[:200]}"
    )


def test_apply_skill_dispatches_format_to_mock_ollama(e2e_stack: None) -> None:
    """The apply_skill stage should send a JSON Schema format= to mock-ollama."""
    _wait_for_skills_messages(timeout=60)
    calls = httpx.get(f"{OLLAMA_URL}/__calls", timeout=5).json()
    assert len(calls) > 0, "mock-ollama received no calls"

    structured_calls = [c for c in calls if isinstance(c.get("format"), dict)]
    assert len(structured_calls) > 0, (
        "no structured-extraction calls received — apply_skill should send format=schema"
    )

    schema = structured_calls[0]["format"]
    assert schema.get("type") == "object"
    properties = schema.get("properties", {})
    assert "summary" in properties
    assert "score" in properties


def test_per_source_llm_dispatches_special_model(e2e_stack: None) -> None:
    """The per-source LLM override should send model=mock-special to mock-ollama."""
    _wait_for_skills_messages(timeout=60)
    calls = httpx.get(f"{OLLAMA_URL}/__calls", timeout=5).json()
    assert len(calls) > 0
    models = {c.get("model") for c in calls}
    assert "mock-special" in models, (
        f"expected the per-source model 'mock-special' to be used, "
        f"but mock-ollama only saw: {models}"
    )
