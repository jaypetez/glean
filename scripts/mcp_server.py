from __future__ import annotations

import os
import re
import sqlite3
import subprocess
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

MAX_OUTPUT_CHARS = 4000
READ_ONLY_SELECT_RE = re.compile(r"^\s*select\b", re.IGNORECASE)
PYTEST_PASSED_RE = re.compile(r"(\d+)\s+passed")
PYTEST_FAILED_RE = re.compile(r"(\d+)\s+failed")
PYTEST_ERRORS_RE = re.compile(r"(\d+)\s+errors?")
MYPY_ERRORS_RE = re.compile(r"Found\s+(\d+)\s+errors?\b")
RUFF_FIXED_RE = re.compile(r"(\d+)\s+fixed\b")
RUFF_REFORMATTED_RE = re.compile(r"(\d+)\s+files?\s+reformatted\b")
ALLOWED_MAKE_TARGETS = {
    "check",
    "test",
    "e2e",
    "ui-test",
    "lint",
    "format",
    "coverage",
    "docs",
    "docs-cli",
    "docs-api",
    "docs-schema",
}

server = FastMCP("glean-dev", json_response=True)



def _truncate_output(text: str, *, limit: int = MAX_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    marker = "\n... [truncated] ...\n"
    head = (limit - len(marker)) // 2
    tail = limit - len(marker) - head
    return f"{text[:head]}{marker}{text[-tail:]}"



def _combine_output(result: subprocess.CompletedProcess[str]) -> str:
    parts = [part for part in (result.stdout, result.stderr) if part]
    return _truncate_output("\n".join(parts).strip())



def _run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        command,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )



def _summary_window(text: str) -> str:
    lines = [line for line in text.splitlines() if line.strip()]
    return "\n".join(lines[-10:])



def _extract_count(pattern: re.Pattern[str], text: str) -> int:
    matches = pattern.findall(text)
    return sum(int(match) for match in matches)



def _result_error(exc: Exception) -> dict[str, str]:
    return {"error": str(exc)}



def _timeout_part(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value



def _timeout_result(exc: subprocess.TimeoutExpired) -> dict[str, str]:
    timeout = int(exc.timeout) if isinstance(exc.timeout, int | float) else exc.timeout
    parts = [_timeout_part(exc.output), _timeout_part(exc.stderr)]
    output = _truncate_output("\n".join(part for part in parts if part).strip())
    return {
        "error": f"Command timed out after {timeout} seconds.",
        "output": output,
    }



def _db_path() -> Path:
    return Path(os.environ.get("GLEAN_DB", "data/state.db"))



@server.tool()
def run_tests(file: str | None = None, keyword: str | None = None) -> dict[str, Any]:
    try:
        command = ["uv", "run", "pytest", "-q"]
        if file:
            command.append(file)
        if keyword:
            command.extend(["-k", keyword])
        result = _run_command(command)
        output = _combine_output(result)
        summary = _summary_window(output)
        return {
            "passed": _extract_count(PYTEST_PASSED_RE, summary),
            "failed": _extract_count(PYTEST_FAILED_RE, summary),
            "errors": _extract_count(PYTEST_ERRORS_RE, summary),
            "output": output,
        }
    except subprocess.TimeoutExpired as exc:
        return _timeout_result(exc)
    except Exception as exc:
        return _result_error(exc)



@server.tool()
def lint_fix() -> dict[str, Any]:
    try:
        check_result = _run_command(["uv", "run", "ruff", "check", "--fix", "src", "tests"])
        format_result = _run_command(["uv", "run", "ruff", "format", "src", "tests"])
        check_output = _combine_output(check_result)
        format_output = _combine_output(format_result)
        output = _truncate_output(
            "\n".join(part for part in (check_output, format_output) if part)
        )
        fixed_count = _extract_count(RUFF_FIXED_RE, check_output)
        fixed_count += _extract_count(RUFF_REFORMATTED_RE, format_output)
        return {"fixed_count": fixed_count, "output": output}
    except subprocess.TimeoutExpired as exc:
        return _timeout_result(exc)
    except Exception as exc:
        return _result_error(exc)



@server.tool()
def type_check() -> dict[str, Any]:
    try:
        result = _run_command(["uv", "run", "mypy", "src"])
        output = _combine_output(result)
        errors = _extract_count(MYPY_ERRORS_RE, _summary_window(output))
        return {"errors": errors, "output": output}
    except subprocess.TimeoutExpired as exc:
        return _timeout_result(exc)
    except Exception as exc:
        return _result_error(exc)



@server.tool()
def validate_config(config_path: str) -> dict[str, Any]:
    try:
        result = _run_command(["uv", "run", "glean", "validate-config", "-c", config_path])
        output = _combine_output(result)
        errors = [line for line in output.splitlines() if line.strip()]
        return {"valid": result.returncode == 0, "errors": [] if result.returncode == 0 else errors}
    except subprocess.TimeoutExpired as exc:
        return _timeout_result(exc)
    except Exception as exc:
        return _result_error(exc)



@server.tool()
def query_db(sql: str) -> dict[str, Any]:
    try:
        if not READ_ONLY_SELECT_RE.match(sql):
            return {"error": "Only SELECT statements are allowed."}

        db_path = _db_path()
        if not db_path.exists():
            return {"error": f"Database not found: {db_path}"}

        connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(sql).fetchmany(100)
            data = [dict(row) for row in rows]
        finally:
            connection.close()

        return {"rows": data, "count": len(data)}
    except Exception as exc:
        return _result_error(exc)



def _select_container() -> str | None:
    result = _run_command(["docker", "ps", "--format", "{{.Names}}"])
    if result.returncode != 0:
        return None
    containers = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    if "glean-e2e" in containers:
        return "glean-e2e"
    if "glean" in containers:
        return "glean"
    return None



@server.tool()
def get_logs(feed: str | None = None, lines: int = 100) -> dict[str, Any]:
    try:
        try:
            container = _select_container()
        except FileNotFoundError:
            return {"container": None, "line_count": 0, "output": "Docker is not available."}

        if container is None:
            return {"container": None, "line_count": 0, "output": "No glean container is running."}

        tail = max(lines * 5, 200) if feed else max(lines, 1)
        result = _run_command(["docker", "logs", container, "--tail", str(tail)])
        if result.returncode != 0:
            message = _combine_output(result) or f"No logs available for container: {container}"
            return {"container": container, "line_count": 0, "output": message}

        log_lines = result.stdout.splitlines()
        if feed:
            log_lines = [line for line in log_lines if feed in line]
        log_lines = log_lines[-max(lines, 1) :]
        output = _truncate_output("\n".join(log_lines))
        return {"container": container, "line_count": len(log_lines), "output": output}
    except subprocess.TimeoutExpired as exc:
        return _timeout_result(exc)
    except Exception as exc:
        return _result_error(exc)



@server.tool()
def make_target(target: str) -> dict[str, Any]:
    try:
        if target not in ALLOWED_MAKE_TARGETS:
            return {"error": f"Unsupported make target: {target}"}
        result = _run_command(["make", target])
        return {
            "target": target,
            "returncode": result.returncode,
            "output": _combine_output(result),
        }
    except subprocess.TimeoutExpired as exc:
        return _timeout_result(exc)
    except Exception as exc:
        return _result_error(exc)



if __name__ == "__main__":
    server.run()
