"""Config-related service functions used by CLI + API."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from glean.config import load_config


@dataclass(frozen=True, slots=True)
class FeedSummary:
    name: str
    schedule: str
    sources_count: int


@dataclass(frozen=True, slots=True)
class ConfigSummary:
    path: Path
    feeds_count: int
    feeds: list[FeedSummary]


def validate_config_summary(path: Path) -> ConfigSummary:
    """Load + validate a config file. Raises ConfigError on failure.

    Returns a structured summary with feed counts and per-feed metadata.
    """
    cfg = load_config(path)
    return ConfigSummary(
        path=path,
        feeds_count=len(cfg.feeds),
        feeds=[
            FeedSummary(
                name=feed.name,
                schedule=feed.schedule,
                sources_count=len(feed.sources),
            )
            for feed in cfg.feeds
        ],
    )
