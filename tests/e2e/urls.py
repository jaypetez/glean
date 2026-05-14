from __future__ import annotations

import os


def _url(name: str, default_port: int) -> str:
    explicit = os.environ.get(f"GLEAN_E2E_{name}_URL")
    if explicit:
        return explicit.rstrip("/")
    port = os.environ.get(f"GLEAN_E2E_{name}_PORT", str(default_port))
    return f"http://localhost:{port}"


TELEGRAM_URL = _url("TELEGRAM", 8001)
OLLAMA_URL = _url("OLLAMA", 11434)
RSS_URL = _url("RSS", 8002)
SEARXNG_URL = _url("SEARXNG", 8003)
