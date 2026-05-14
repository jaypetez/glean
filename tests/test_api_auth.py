from __future__ import annotations

import logging
from pathlib import Path

import pytest


def test_initial_api_key_logged_once_on_first_creation(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    from glean.api.auth import get_or_create_api_key

    caplog.set_level(logging.WARNING, logger="glean.initial_api_key")

    material = get_or_create_api_key(tmp_path / "state.db")

    assert material.plaintext is not None
    messages = [
        record.getMessage()
        for record in caplog.records
        if record.name == "glean.initial_api_key"
    ]
    assert messages == [f"GLEAN_INITIAL_API_KEY={material.plaintext}"]
    assert "initial_key_logged=1" in (tmp_path / "api_key").read_text(encoding="utf-8")

    caplog.clear()
    restarted = get_or_create_api_key(tmp_path / "state.db")

    assert restarted.plaintext is None
    assert [
        record.getMessage()
        for record in caplog.records
        if record.name == "glean.initial_api_key"
    ] == []
