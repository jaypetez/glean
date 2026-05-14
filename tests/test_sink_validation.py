from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from glean.config.schema import Config
from glean.sinks import build_sink

pytestmark = pytest.mark.asyncio


def _config_with_sink(spec: dict[str, Any]) -> Config:
    return Config.model_validate(
        {
            "feeds": [
                {
                    "name": "sink-validation",
                    "schedule": "every 1h",
                    "sinks": [spec],
                    "sources": [{"type": "fake"}],
                    "pipeline": ["dedup"],
                }
            ]
        }
    )


def _assert_config_rejects(spec: dict[str, Any], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        _config_with_sink(spec)


def _assert_construction_rejects(spec: dict[str, Any], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        build_sink(spec)


async def _assert_constructs(spec: dict[str, Any]) -> None:
    sink = build_sink(spec)
    try:
        assert sink.required is True
    finally:
        await sink.aclose()


@pytest.mark.parametrize(
    "webhook_url",
    [
        "https://discord.com/api/webhooks/not-a-number/token",
        "https://discord.com/api/webhooks/123456/ABCdef123\n",
    ],
)
async def test_discord_rejects_invalid_webhook_url_at_config_and_construction(
    webhook_url: str,
) -> None:
    spec = {"type": "discord", "webhook_url": webhook_url}

    _assert_config_rejects(spec, "Discord webhook URL")
    _assert_construction_rejects(spec, "Discord webhook URL")


async def test_discord_accepts_valid_webhook_url_at_config_and_construction() -> None:
    spec = {
        "type": "discord",
        "webhook_url": "https://discord.com/api/webhooks/123456/ABC_def-ghi.jkl",
    }

    cfg = _config_with_sink(spec)
    assert cfg.feeds[0].sinks == [spec]
    await _assert_constructs(spec)


async def test_discord_rejects_bad_avatar_scheme_at_config_and_construction() -> None:
    spec = {
        "type": "discord",
        "webhook_url": "https://discord.com/api/webhooks/123456/ABCdef123",
        "avatar_url": "javascript:alert(1)",
    }

    _assert_config_rejects(spec, "avatar_url|scheme")
    _assert_construction_rejects(spec, "avatar_url|scheme")


async def test_discord_rejects_blocked_avatar_url_at_config_and_construction() -> None:
    spec = {
        "type": "discord",
        "webhook_url": "https://discord.com/api/webhooks/123456/ABCdef123",
        "avatar_url": "http://10.0.0.1/avatar.png",
    }

    _assert_config_rejects(spec, "avatar_url")
    _assert_construction_rejects(spec, "avatar_url")


@pytest.mark.parametrize(
    "webhook_url",
    [
        "https://hooks.slack.com/services/not/a/slack-webhook",
        "https://hooks.slack.com/services/TABC123/BDEF456/aBc123XYZ\n",
    ],
)
async def test_slack_rejects_invalid_webhook_url_at_config_and_construction(
    webhook_url: str,
) -> None:
    spec = {"type": "slack", "webhook_url": webhook_url}

    _assert_config_rejects(spec, "Slack webhook URL")
    _assert_construction_rejects(spec, "Slack webhook URL")


async def test_slack_accepts_valid_webhook_url_at_config_and_construction() -> None:
    spec = {
        "type": "slack",
        "webhook_url": "https://hooks.slack.com/services/TABC123/BDEF456/aBc123XYZ",
    }

    cfg = _config_with_sink(spec)
    assert cfg.feeds[0].sinks == [spec]
    await _assert_constructs(spec)


@pytest.mark.parametrize("topic", ["../secret", "x" * 65, "alerts\n"])
async def test_ntfy_rejects_invalid_topic_at_config_and_construction(topic: str) -> None:
    spec = {"type": "ntfy", "topic": topic}

    _assert_config_rejects(spec, "ntfy topic")
    _assert_construction_rejects(spec, "ntfy topic")


async def test_ntfy_accepts_valid_topic_at_config_and_construction() -> None:
    spec = {"type": "ntfy", "topic": "alerts_1-OK"}

    cfg = _config_with_sink(spec)
    assert cfg.feeds[0].sinks == [spec]
    await _assert_constructs(spec)


async def test_file_rejects_path_outside_allowed_roots_at_config_and_construction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    allowed_root = tmp_path / "allowed"
    outside = tmp_path / "outside" / "out.txt"
    monkeypatch.setenv("GLEAN_FILE_SINK_ROOTS", str(allowed_root))
    spec = {"type": "file", "path": str(outside)}

    _assert_config_rejects(spec, "outside allowed roots")
    _assert_construction_rejects(spec, "outside allowed roots")


async def test_file_rejects_prefix_bypass_at_config_and_construction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    allowed_root = tmp_path / "data"
    sibling = tmp_path / "data2" / "out.txt"
    monkeypatch.setenv("GLEAN_FILE_SINK_ROOTS", str(allowed_root))
    spec = {"type": "file", "path": str(sibling)}

    _assert_config_rejects(spec, "outside allowed roots")
    _assert_construction_rejects(spec, "outside allowed roots")


async def test_file_rejects_root_itself_at_config_and_construction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    allowed_root = tmp_path / "allowed"
    monkeypatch.setenv("GLEAN_FILE_SINK_ROOTS", str(allowed_root))
    spec = {"type": "file", "path": str(allowed_root)}

    _assert_config_rejects(spec, "must name a file")
    _assert_construction_rejects(spec, "must name a file")


async def test_file_rejects_deep_nesting_at_config_and_construction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    allowed_root = tmp_path / "allowed"
    deep_path = allowed_root.joinpath(
        "level01",
        "level02",
        "level03",
        "level04",
        "level05",
        "level06",
        "level07",
        "level08",
        "level09",
        "level10",
        "level11",
        "out.txt",
    )
    monkeypatch.setenv("GLEAN_FILE_SINK_ROOTS", str(allowed_root))
    spec = {"type": "file", "path": str(deep_path)}

    _assert_config_rejects(spec, "more than 10 path segments")
    _assert_construction_rejects(spec, "more than 10 path segments")


async def test_file_accepts_path_under_configured_root_at_config_and_construction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    allowed_root = tmp_path / "allowed"
    out = allowed_root / "archive" / "out.jsonl"
    monkeypatch.setenv("GLEAN_FILE_SINK_ROOTS", str(allowed_root))
    spec = {"type": "file", "path": str(out), "format": "jsonl"}

    cfg = _config_with_sink(spec)
    assert cfg.feeds[0].sinks == [spec]
    await _assert_constructs(spec)
