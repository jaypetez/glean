from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path

import pytest

from scripts import mcp_server


def _completed(
    *,
    stdout: str = "",
    stderr: str = "",
    returncode: int = 0,
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["uv"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def test_run_tests_builds_pytest_command_and_parses_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_run(
        cmd: list[str],
        *,
        capture_output: bool,
        text: bool,
        timeout: int,
        check: bool,
    ):
        captured["cmd"] = cmd
        captured["capture_output"] = capture_output
        captured["text"] = text
        captured["timeout"] = timeout
        captured["check"] = check
        return _completed(stdout="..F\nE\n2 passed, 1 failed, 1 error in 0.12s\n")

    monkeypatch.setattr(mcp_server.subprocess, "run", fake_run)

    result = mcp_server.run_tests(file="tests/test_runner.py", keyword="score")

    assert captured == {
        "cmd": ["uv", "run", "pytest", "-q", "tests/test_runner.py", "-k", "score"],
        "capture_output": True,
        "text": True,
        "timeout": 300,
        "check": False,
    }
    assert result["passed"] == 2
    assert result["failed"] == 1
    assert result["errors"] == 1
    assert "2 passed, 1 failed, 1 error" in result["output"]


def test_lint_fix_runs_ruff_commands_and_counts_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    responses = [
        _completed(stdout="Found 3 errors (2 fixed, 1 remaining).\n"),
        _completed(stdout="1 file reformatted, 4 files left unchanged\n"),
    ]

    def fake_run(
        cmd: list[str],
        *,
        capture_output: bool,
        text: bool,
        timeout: int,
        check: bool,
    ):
        calls.append(cmd)
        assert check is False
        return responses.pop(0)

    monkeypatch.setattr(mcp_server.subprocess, "run", fake_run)

    result = mcp_server.lint_fix()

    assert calls == [
        ["uv", "run", "ruff", "check", "--fix", "src", "tests"],
        ["uv", "run", "ruff", "format", "src", "tests"],
    ]
    assert result["fixed_count"] == 3
    assert "Found 3 errors" in result["output"]
    assert "1 file reformatted" in result["output"]


def test_type_check_parses_mypy_error_count(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(
        cmd: list[str],
        *,
        capture_output: bool,
        text: bool,
        timeout: int,
        check: bool,
    ):
        assert cmd == ["uv", "run", "mypy", "src"]
        assert check is False
        return _completed(
            stdout=(
                "src/glean/example.py:1: error: Example failure [misc]\n"
                "Found 1 error in 1 file (checked 42 source files)\n"
            ),
            returncode=1,
        )

    monkeypatch.setattr(mcp_server.subprocess, "run", fake_run)

    result = mcp_server.type_check()

    assert result["errors"] == 1
    assert "Found 1 error" in result["output"]


def test_validate_config_returns_invalid_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(
        cmd: list[str],
        *,
        capture_output: bool,
        text: bool,
        timeout: int,
        check: bool,
    ):
        assert cmd == ["uv", "run", "glean", "validate-config", "-c", "feeds.yaml"]
        assert check is False
        return _completed(
            stderr="config file not found: feeds.yaml\nfailed to load config\n",
            returncode=1,
        )

    monkeypatch.setattr(mcp_server.subprocess, "run", fake_run)

    result = mcp_server.validate_config("feeds.yaml")

    assert result == {
        "valid": False,
        "errors": ["config file not found: feeds.yaml", "failed to load config"],
    }


def test_query_db_rejects_non_select_statements(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GLEAN_DB", "ignored.db")

    result = mcp_server.query_db("DELETE FROM seen_items")

    assert result == {"error": "Only SELECT statements are allowed."}


def test_query_db_returns_first_hundred_rows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "state.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("CREATE TABLE items(id INTEGER PRIMARY KEY, name TEXT)")
        connection.executemany(
            "INSERT INTO items(name) VALUES (?)",
            [(f"item-{index}",) for index in range(105)],
        )
        connection.commit()
    finally:
        connection.close()

    monkeypatch.setenv("GLEAN_DB", str(db_path))

    result = mcp_server.query_db("SELECT id, name FROM items ORDER BY id")

    assert result["count"] == 100
    assert len(result["rows"]) == 100
    assert result["rows"][0]["name"] == "item-0"
    assert result["rows"][-1]["name"] == "item-99"


def test_get_logs_prefers_e2e_container_and_filters_feed(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(
        cmd: list[str],
        *,
        capture_output: bool,
        text: bool,
        timeout: int,
        check: bool,
    ):
        calls.append(cmd)
        assert check is False
        if cmd[:3] == ["docker", "ps", "--format"]:
            return _completed(stdout="glean-e2e\nglean\n")
        assert cmd == ["docker", "logs", "glean-e2e", "--tail", "200"]
        return _completed(stdout="feed=ops first\nfeed=ai ignore\nfeed=ops second\n")

    monkeypatch.setattr(mcp_server.subprocess, "run", fake_run)

    result = mcp_server.get_logs(feed="ops", lines=2)

    assert calls[0] == ["docker", "ps", "--format", "{{.Names}}"]
    assert result["container"] == "glean-e2e"
    assert result["line_count"] == 2
    assert result["output"] == "feed=ops first\nfeed=ops second"


def test_make_target_rejects_unknown_targets() -> None:
    result = mcp_server.make_target("deploy")

    assert result == {"error": "Unsupported make target: deploy"}



def test_make_target_returns_partial_output_on_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(
        cmd: list[str],
        *,
        capture_output: bool,
        text: bool,
        timeout: int,
        check: bool,
    ):
        raise subprocess.TimeoutExpired(
            cmd=cmd,
            timeout=timeout,
            output="step one\nstep two\n",
            stderr="still running\n",
        )

    monkeypatch.setattr(mcp_server.subprocess, "run", fake_run)

    result = mcp_server.make_target("e2e")

    assert result["error"] == "Command timed out after 300 seconds."
    assert result["output"] == "step one\nstep two\n\nstill running"



def test_get_logs_reports_when_no_matching_container_is_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(
        cmd: list[str],
        *,
        capture_output: bool,
        text: bool,
        timeout: int,
        check: bool,
    ):
        if cmd[:3] == ["docker", "ps", "--format"]:
            return _completed(stdout="postgres\nredis\n")
        pytest.fail(f"unexpected command: {cmd}")

    monkeypatch.setattr(mcp_server.subprocess, "run", fake_run)

    result = mcp_server.get_logs()

    assert result == {
        "container": None,
        "line_count": 0,
        "output": "No glean container is running.",
    }
