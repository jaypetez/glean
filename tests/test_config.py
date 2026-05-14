from __future__ import annotations

import textwrap

import pytest

from glean.config import load_config
from glean.config.loader import ConfigError


def _minimal(extra: str = "") -> str:
    return textwrap.dedent(
        f"""
        defaults:
          llm:
            provider: ollama
            model: qwen2.5:7b
            base_url: http://ollama:11434

        feeds:
          - name: ai
            schedule: "every 1h"
            chat_id: -1001
            sources:
              - type: rss
                url: https://example.com/feed
            pipeline:
              - dedup
              - summarize:
                  prompt: "summarize"
              - digest:
                  intro: "hello"
        {extra}
        """
    )


def test_load_minimal(write_yaml) -> None:
    cfg = load_config(write_yaml(_minimal()))
    assert len(cfg.feeds) == 1
    feed = cfg.feeds[0]
    assert feed.name == "ai"
    assert feed.chat_id == -1001
    assert feed.effective_llm(cfg.defaults).provider == "ollama"


def test_effective_sinks_inherits_from_defaults_sinks(write_yaml) -> None:
    yaml = textwrap.dedent(
        """
        defaults:
          sinks:
            - type: telegram
              chat_id: -100999
        feeds:
          - name: ai
            schedule: "every 1h"
            sources:
              - type: rss
                url: https://example.com/feed
            pipeline:
              - dedup
        """
    )
    cfg = load_config(write_yaml(yaml))

    assert cfg.feeds[0].effective_sinks(cfg.defaults) == [
        {"type": "telegram", "chat_id": -100999}
    ]


def test_effective_sinks_inherits_from_telegram_defaults(write_yaml) -> None:
    yaml = textwrap.dedent(
        """
        defaults:
          telegram:
            bot_token: test-token
            chat_id: -100123
        feeds:
          - name: ai
            schedule: "every 1h"
            sources:
              - type: rss
                url: https://example.com/feed
            pipeline:
              - dedup
        """
    )
    cfg = load_config(write_yaml(yaml))

    assert cfg.feeds[0].effective_sinks(cfg.defaults) == [
        {"type": "telegram", "chat_id": -100123, "token": "test-token"}
    ]


def test_effective_sinks_raises_without_feed_or_default_sinks(write_yaml) -> None:
    yaml = textwrap.dedent(
        """
        feeds:
          - name: ai
            schedule: "every 1h"
            sources:
              - type: rss
                url: https://example.com/feed
            pipeline:
              - dedup
        """
    )
    cfg = load_config(write_yaml(yaml))

    with pytest.raises(ValueError, match="feed must have feed-level sinks"):
        cfg.feeds[0].effective_sinks(cfg.defaults)


def test_env_interpolation(write_yaml, monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_CHAT_AI", "-1009")
    yaml = textwrap.dedent(
        """
        feeds:
          - name: ai
            schedule: "every 1h"
            chat_id: ${TELEGRAM_CHAT_AI}
            sources:
              - type: rss
                url: https://example.com/feed
            pipeline:
              - dedup
        """
    )
    cfg = load_config(write_yaml(yaml))
    # chat_id comes back as string after interpolation since it was a template
    assert str(cfg.feeds[0].chat_id) == "-1009"


def test_missing_env_var_is_error(write_yaml) -> None:
    yaml = textwrap.dedent(
        """
        feeds:
          - name: ai
            schedule: "every 1h"
            chat_id: ${NOT_SET}
            sources:
              - type: rss
                url: https://example.com/feed
            pipeline:
              - dedup
        """
    )
    with pytest.raises(ConfigError) as exc:
        load_config(write_yaml(yaml))
    assert "NOT_SET" in str(exc.value)


def test_duplicate_feed_names_rejected(write_yaml) -> None:
    yaml = textwrap.dedent(
        """
        feeds:
          - name: ai
            schedule: "every 1h"
            chat_id: -1
            sources:
              - type: rss
                url: https://example.com/feed
            pipeline:
              - dedup
          - name: ai
            schedule: "every 2h"
            chat_id: -2
            sources:
              - type: rss
                url: https://example.com/feed
            pipeline:
              - dedup
        """
    )
    with pytest.raises(ConfigError):
        load_config(write_yaml(yaml))


def test_bad_schedule_rejected(write_yaml) -> None:
    yaml = textwrap.dedent(
        """
        feeds:
          - name: ai
            schedule: "nonsense"
            chat_id: -1
            sources:
              - type: rss
                url: https://example.com/feed
            pipeline:
              - dedup
        """
    )
    with pytest.raises(ConfigError):
        load_config(write_yaml(yaml))
