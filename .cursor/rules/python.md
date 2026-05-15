---
description: Python coding conventions for glean
globs: ["src/**/*.py", "tests/**/*.py"]
---

# Python conventions

- Every file starts with `from __future__ import annotations`
- Dataclasses use `frozen=True, slots=True`
- Pydantic models use `ConfigDict(extra="forbid")`
- All I/O is async (httpx.AsyncClient, aiosqlite, ollama.AsyncClient)
- Logging via `glean.logging.get_logger(__name__)` — never `print()`
- Validate outbound URLs via `glean.security.ssrf.validate_url(url, allow_private=...)` before any HTTP request
- Use `pass`, not `...`, in empty protocol stubs (CodeQL flags `...`)
- Empty `except: pass` needs an inline comment explaining why (CodeQL flags it otherwise)
- After editing, run: `uv run ruff check --fix src tests && uv run mypy src`
