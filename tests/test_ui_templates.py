from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from glean.config.schedule import parse_schedule
from glean.config.schema import Config

_REPO_ROOT = Path(__file__).resolve().parents[1]
_TEMPLATES_TS = _REPO_ROOT / "ui" / "src" / "lib" / "templates.ts"
_METADATA_KEYS = {"id", "title", "description", "source_labels"}


def _load_templates() -> list[dict[str, Any]]:
    text = _TEMPLATES_TS.read_text(encoding="utf-8")
    match = re.search(
        r"export const feedTemplates: FeedTemplate\[] = (\[.*?\]);",
        text,
        flags=re.DOTALL,
    )
    assert match is not None, "templates.ts must export feedTemplates as a JSON literal"
    templates = json.loads(match.group(1))
    assert isinstance(templates, list)
    return templates


def _feed_payload(template: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in template.items() if key not in _METADATA_KEYS}


def test_starter_templates_are_valid_feed_configs() -> None:
    templates = _load_templates()

    assert [template["id"] for template in templates] == [
        "ai-ml-news",
        "reddit-pulse",
        "web-search-briefing",
        "engineering-blogs",
        "github-trending",
        "custom-blank",
    ]

    for template in templates:
        cfg = Config.model_validate(
            {
                "defaults": {
                    "sinks": [{"type": "telegram", "chat_id": "-1001234567890"}],
                },
                "feeds": [_feed_payload(template)],
            }
        )
        assert cfg.feeds[0].name == template["name"]
        parse_schedule(cfg.feeds[0].schedule)
