from __future__ import annotations

import logging
import os
import sys
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
        record.getMessage() for record in caplog.records if record.name == "glean.initial_api_key"
    ]
    assert messages == [f"GLEAN_INITIAL_API_KEY={material.plaintext}"]
    assert "initial_key_logged=1" in (tmp_path / "api_key").read_text(encoding="utf-8")

    caplog.clear()
    restarted = get_or_create_api_key(tmp_path / "state.db")

    assert restarted.plaintext is None
    assert [
        record.getMessage() for record in caplog.records if record.name == "glean.initial_api_key"
    ] == []


@pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX chmod checks are not reliable on Windows"
)
def test_get_or_create_api_key_rejects_world_readable_verifier_after_create(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from glean.api.auth import get_or_create_api_key

    key_file = tmp_path / "api_key"
    original_stat = Path.stat

    def report_world_readable_mode(self: Path, *, follow_symlinks: bool = True) -> os.stat_result:
        result = original_stat(self, follow_symlinks=follow_symlinks)
        if self == key_file:
            values = list(result)
            values[0] = (result.st_mode & ~0o777) | 0o644
            return os.stat_result(values)
        return result

    monkeypatch.setattr(Path, "stat", report_world_readable_mode)

    with pytest.raises(RuntimeError, match="/data/api_key.*chmod 600"):
        get_or_create_api_key(tmp_path / "state.db")


@pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX chmod checks are not reliable on Windows"
)
def test_get_or_create_api_key_rejects_existing_world_readable_verifier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from glean.api.auth import get_or_create_api_key

    key_file = tmp_path / "api_key"
    get_or_create_api_key(tmp_path / "state.db")
    original_stat = Path.stat

    def report_world_readable_mode(self: Path, *, follow_symlinks: bool = True) -> os.stat_result:
        result = original_stat(self, follow_symlinks=follow_symlinks)
        if self == key_file:
            values = list(result)
            values[0] = (result.st_mode & ~0o777) | 0o644
            return os.stat_result(values)
        return result

    monkeypatch.setattr(Path, "stat", report_world_readable_mode)

    with pytest.raises(RuntimeError, match="/data/api_key.*chmod 600"):
        get_or_create_api_key(tmp_path / "state.db")
