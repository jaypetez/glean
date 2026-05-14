from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for key in [
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_AI",
        "TELEGRAM_CHAT_SEC",
        "TELEGRAM_CHAT_HN",
        "TELEGRAM_OPS_CHAT_ID",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "BRAVE_API_KEY",
        "TAVILY_API_KEY",
        "SERPER_API_KEY",
        "EXA_API_KEY",
        "SEARXNG_URL",
        "SEARCH_ENGINE",
        "GLEAN_SSRF_ALLOWED_HOSTS",
        "GLEAN_FILE_SINK_ROOTS",
    ]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("GLEAN_FILE_SINK_ROOTS", str(tmp_path))


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    return tmp_path / "state.db"


@pytest.fixture
def write_yaml(tmp_path: Path):
    def _write(text: str, name: str = "feeds.yaml") -> Path:
        path = tmp_path / name
        path.write_text(text, encoding="utf-8")
        return path

    return _write


@pytest.fixture
async def http_client():
    """Async httpx client for source/llm tests."""
    import httpx

    async with httpx.AsyncClient(timeout=10.0) as client:
        yield client


@pytest.fixture
async def state_store(tmp_db: Path):
    """Open a StateStore for tests that need ETag caching."""
    from glean.state.store import StateStore

    store = StateStore(tmp_db)
    await store.open()
    try:
        yield store
    finally:
        await store.close()


@pytest.fixture
def fetch_context(http_client, state_store):
    """A FetchContext suitable for source.fetch() calls."""
    from glean.sources.base import FetchContext

    return FetchContext(feed_name="test", http=http_client, state=state_store)
