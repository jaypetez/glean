"""Config-related service functions used by CLI + API."""

from __future__ import annotations

import io
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from glean.config import Config, load_config

_ENV_RE = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")


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


def _resolve_env_placeholders(value: str) -> str:
    def repl(match: re.Match[str]) -> str:
        name = match.group(1)
        return os.environ.get(name, match.group(0))

    return _ENV_RE.sub(repl, value)


def _load_existing_yaml(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    yaml = YAML(typ="safe")
    try:
        raw = yaml.load(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return raw if isinstance(raw, dict) else None


def _raw_item_for_value(
    value: Any,
    raw: list[Any],
    raw_by_name: dict[str, Any],
    index: int,
) -> Any:
    if isinstance(value, dict):
        name = value.get("name")
        if isinstance(name, str) and name in raw_by_name:
            return raw_by_name[name]
    return raw[index] if index < len(raw) else None


def _preserve_env_placeholders(value: Any, raw: Any) -> Any:
    if isinstance(value, dict) and isinstance(raw, dict):
        return {key: _preserve_env_placeholders(val, raw.get(key)) for key, val in value.items()}
    if isinstance(value, list) and isinstance(raw, list):
        raw_by_name = {
            item["name"]: item
            for item in raw
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        }
        return [
            _preserve_env_placeholders(val, _raw_item_for_value(val, raw, raw_by_name, index))
            for index, val in enumerate(value)
        ]
    if isinstance(raw, str) and _ENV_RE.search(raw):
        resolved = _resolve_env_placeholders(raw)
        if isinstance(value, str) and value == resolved:
            return raw
        if not isinstance(value, str | dict | list) and str(value) == resolved:
            return raw
    return value


def write_config(cfg: Config, path: Path) -> None:
    """Write the Config back to YAML at ``path``.

    Uses ruamel.yaml in safe mode so the on-disk format stays clean and
    deterministic. Comments are not preserved across full rewrites. Existing
    ${VAR} references are preserved when their resolved values are unchanged.
    The write is atomic via write-to-temp + rename.
    """
    serialized = _config_to_yaml_data(cfg)
    if raw := _load_existing_yaml(path):
        serialized = _preserve_env_placeholders(serialized, raw)
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
