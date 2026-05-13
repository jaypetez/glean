# Copilot Instructions for glean

## Build, Lint, and Test

```bash
uv venv && uv pip install -e ".[dev]"

ruff check src tests        # lint
mypy src                    # type-check (strict mode)
pytest -q                   # all tests

pytest tests/test_schedule.py            # one test file
pytest tests/test_runner.py::test_bootstrap_skips_send  # one test function
pytest -k "score"                        # tests matching keyword
```

CI runs `ruff check` → `mypy` → `pytest` in that order. All three must pass.

## Architecture

glean is an async Python daemon that runs **feeds** on a schedule. Each feed is a pipeline: `sources → dedup → rank → summarize → digest → send`. Configuration lives in `feeds.yaml` (Pydantic v2 models in `config/schema.py`, loaded with env-var interpolation in `config/loader.py`).

### Plugin system

Two parallel plugin registries using decorator-based registration:

- **Sources** — implement `Source` protocol (`async fetch(ctx) -> list[Item]`), register with `@register_source("type_name")`. See `sources/rss.py` for the minimal example.
- **LLM providers** — implement `LLMProvider` protocol (`rank`, `summarize`, `digest`, `aclose`), register with `@register_provider("name")`. See `llm/ollama_provider.py`.

Both registries auto-import builtins at module load via `_import_builtins()` in their respective `registry.py` files. New plugins are picked up by adding an import there.

### Key modules

- `pipeline/engine.py` — `Runner` class orchestrates per-feed execution, caches LLM providers by `(provider, model, base_url)` key.
- `pipeline/stages.py` — individual stage functions (`dedup_stage`, `rank_stage`, `summarize_stage`, `digest_intro`). Rank and summarize are concurrency-bounded with `asyncio.Semaphore(4)`.
- `state/store.py` — `StateStore` wraps aiosqlite. Tables: `seen_items`, `feed_runs`, `etag_cache`. Bootstrap logic marks all items as seen on first run.
- `config/schedule.py` — parses friendly schedule strings (`every 1h`, `daily 09:00`, cron) into `IntervalSchedule | CronSchedule`.
- `telegram/render.py` — renders digests into Telegram-safe message chunks (4096-char limit, HTML/Markdown/plain).

### Data flow

`Item` is a frozen slotted dataclass (`sources/base.py`). Pipeline stages produce new `Item` instances via `dataclasses.replace()` to attach `llm_summary` and `relevance` scores — items are never mutated.

## Conventions

- **Every Python file starts with** `from __future__ import annotations`.
- **Dataclasses use** `frozen=True, slots=True` for immutability and performance.
- **Pydantic models use** `ConfigDict(extra="forbid")` to reject unknown fields.
- **Logging** uses `structlog` via `glean.logging.get_logger(__name__)` — structured key=value in dev, JSON when `LOG_FORMAT=json`.
- **All I/O is async** — `httpx.AsyncClient` for HTTP, `aiosqlite` for SQLite, `ollama.AsyncClient` for Ollama.
- **TYPE_CHECKING guard** — heavy imports used only for type hints go behind `if TYPE_CHECKING:`.
- **Ruff config** — line length 100, targets Python 3.12, permits asserts (`S101` ignored), permits many kwargs (`PLR0913` ignored). Tests additionally ignore security rules and late imports.
- **mypy** runs in `strict` mode with `disallow_untyped_defs`.
- **Feed names** must match `^[a-z0-9][a-z0-9._-]*$`.

### Testing patterns

- Tests use `pytest-asyncio` with `asyncio_mode = "auto"` — async test functions work without a decorator.
- Network calls are mocked with `respx` (already a dev dependency).
- Tests register `FakeSource` and `FakeLLM` via the same `@register_source`/`@register_provider` decorators used by real plugins.
- A `conftest.py` autouse fixture strips all secret env vars (`TELEGRAM_BOT_TOKEN`, API keys, etc.) to prevent accidental real calls.
- `write_yaml` fixture creates temporary config files; `tmp_db` fixture provides an isolated database path.

### Adding a new plugin

1. Create a file in `sources/` or `llm/`.
2. Implement the protocol and decorate with `@register_source("name")` or `@register_provider("name")`.
3. Add the import to `_import_builtins()` in the corresponding `registry.py`.
4. Add a unit test (mock network with `respx`), a snippet in `feeds.example.yaml`, and a row in the README table.

### Branch naming

Use `feat/<slug>`, `fix/<slug>`, `docs/<slug>`, or `chore/<slug>`. PRs are squash-merged.
