from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
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
    ]:
        monkeypatch.delenv(key, raising=False)


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
