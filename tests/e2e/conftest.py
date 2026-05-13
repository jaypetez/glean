"""E2E test fixtures: spin up docker-compose stack."""
from __future__ import annotations

import subprocess
import time
from collections.abc import Generator
from pathlib import Path

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO_ROOT / "docker-compose.e2e.yml"


def _compose(*args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_FILE), *args],
        cwd=str(REPO_ROOT),
        check=False,
        capture_output=True,
    )


def _wait_for(url: str, timeout: float = 60.0) -> None:
    """Poll a URL until it returns 200 or the timeout expires."""
    deadline = time.monotonic() + timeout
    last_exc: Exception | None = None
    while time.monotonic() < deadline:
        try:
            r = httpx.get(url, timeout=2.0)
            if r.status_code == 200:
                return
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
        time.sleep(1)
    raise TimeoutError(f"timed out waiting for {url}: {last_exc}")


@pytest.fixture(scope="session")
def e2e_stack() -> Generator[None, None, None]:
    """Start docker-compose.e2e.yml for the session, tear down at the end."""
    if not _compose_available():
        pytest.skip("docker compose not available in this environment")

    # Build & start
    build = _compose("build")
    if build.returncode != 0:
        pytest.fail(
            f"docker compose build failed:\n{build.stdout.decode()}\n{build.stderr.decode()}"
        )

    up = _compose("up", "-d")
    if up.returncode != 0:
        pytest.fail(
            f"docker compose up failed:\n{up.stdout.decode()}\n{up.stderr.decode()}"
        )

    try:
        # Wait for mocks to be healthy
        _wait_for("http://localhost:8001/health", timeout=60)
        _wait_for("http://localhost:11434/health", timeout=60)
        _wait_for("http://localhost:8002/health", timeout=60)
        _wait_for("http://localhost:8003/health", timeout=60)

        yield
    finally:
        logs = _compose("logs", "glean")
        # Always print logs so failed tests have context
        print("---- glean logs (last 100 lines) ----")
        print(logs.stdout.decode("utf-8", errors="replace")[-8000:])

        _compose("down", "-v")


def _compose_available() -> bool:
    try:
        r = subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            check=False,
            timeout=5,
        )
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


@pytest.fixture
def reset_mocks(e2e_stack: None) -> None:
    """Reset mock service state before a test."""
    httpx.post("http://localhost:8001/__reset", timeout=5)
    httpx.post("http://localhost:11434/__reset", timeout=5)
    httpx.post("http://localhost:8002/__reset", timeout=5)
    httpx.post("http://localhost:8003/__reset", timeout=5)
