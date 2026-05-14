"""Config-related service functions used by CLI + API."""
from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from glean.config import Config, load_config


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


def _stage_to_yaml(stage: dict[str, Any]) -> str | dict[str, Any]:
    """Convert a dumped StageSpec back to the YAML shape accepted by the loader."""
    name = stage["name"]
    params = stage.get("params") or {}
    if not params:
        return str(name)
    return {str(name): params}


def _config_to_yaml_data(cfg: Config) -> dict[str, Any]:
    """Serialize Config into the user-facing YAML schema."""
    data = cfg.model_dump(exclude_none=True, mode="json")
    for feed in data.get("feeds", []):
        feed["pipeline"] = [_stage_to_yaml(stage) for stage in feed.get("pipeline", [])]
    return data


def write_config(cfg: Config, path: Path) -> None:
    """Write the Config back to YAML at ``path``.

    Uses ruamel.yaml in safe mode so the on-disk format stays clean and
    deterministic. Comments are not preserved across full rewrites. The write
    is atomic via write-to-temp + rename.
    """
    serialized = _config_to_yaml_data(cfg)
    yaml = YAML(typ="safe")
    yaml.default_flow_style = False
    yaml.indent(mapping=2, sequence=4, offset=2)
    buf = io.StringIO()
    yaml.dump(serialized, buf)
    text = buf.getvalue()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
