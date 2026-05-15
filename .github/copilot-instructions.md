# Copilot Instructions for glean

`glean` is an async Python daemon (Python 3.12+) that runs **feeds** on a schedule. Each feed is a pipeline: `sources → dedup → rank → summarize → apply_skill → digest → sinks`. Configuration lives in `feeds.yaml` and a built-in FastAPI + Svelte UI at port 9090 manages it.

## Build, lint, test

```bash
uv venv && uv pip install -e ".[dev]"

# the gates CI enforces (all must pass)
uv run ruff check src tests        # lint
uv run mypy src                    # type-check (strict mode)
uv run pytest -q                   # unit tests (e2e marker excluded by addopts)

# single test
uv run pytest tests/test_runner.py -q
uv run pytest tests/test_runner.py::test_bootstrap_skips_send -q
uv run pytest -k "score"            # by keyword

# Docker e2e suite (mock telegram/ollama/rss/searxng — no real APIs)
docker compose -f docker-compose.e2e.yml up --build -d
uv run pytest tests/e2e -v -m e2e
docker compose -f docker-compose.e2e.yml down -v

# UI build + Playwright e2e (chromium)
cd ui && npm ci
cd ui && npm run build
cd ui && npx playwright install chromium
cd ui && npx playwright test --workers=1   # 13 specs incl axe-core a11y + visual snapshots

# security scanners (run by CI but useful locally)
uv run pip-audit --strict
uv run bandit -r src --severity-level low --confidence-level low
trivy fs --severity HIGH,CRITICAL .
```

`pyproject.toml` is the single source of truth for ruff/mypy/pytest config. mypy is **strict** (`disallow_untyped_defs`, `warn_return_any`, `warn_unused_ignores`).

CI required checks (all 11): `Lint, type-check, test`, `Audit Python deps`, `Trivy filesystem scan`, `Secret scan` (gitleaks), `Bandit SAST`, `End-to-end (docker compose)`, `e2e-ui` (Playwright), `Container scan`, `CodeQL`, `Analyze Python`, `Dependency review`. All must pass — `enforce_admins: true`, no `--admin` bypass.

## Architecture

Single Docker container, single process. Inside that process:

1. **APScheduler** ticks one feed at a time per its schedule.
2. **`src/glean/pipeline/engine.py::Runner.run_feed`** orchestrates: fetch sources → bootstrap branch (skip-and-mark first run) → dedup against SQLite `seen_items` → run pipeline stages declared in YAML → render → fan out to sinks → record success/failure.
3. **FastAPI** (`src/glean/api/app.py`) shares the same asyncio event loop and serves `/api/v1/*` REST + SSE event stream + the built Svelte SPA at `/`.
4. **Svelte 5 + Vite + Tailwind v4** UI (`ui/`) auths via `X-Glean-Api-Key` header, talks only to the local API.

The CLI (`src/glean/cli/app.py`) and the API both call into a shared service layer (`src/glean/api_service/`) — they never disagree on truth because they share code, not RPC.

### Plugin layers (4)

All four use the same `@register_*` decorator pattern + module-level `_import_builtins()` to wire built-ins:

| Plugin | Protocol | Decorator | Registry | Smallest example |
|---|---|---|---|---|
| Source | `async fetch(ctx) -> list[Item]` | `@register_source("type")` | `src/glean/sources/registry.py` | `sources/rss.py` |
| LLM Provider | `rank` / `summarize` / `digest` / `extract` / `aclose` | `@register_provider("name")` | `src/glean/llm/registry.py` | `llm/ollama_provider.py` |
| Sink | `async send(ctx) -> None` / `aclose` | `@register_sink("type")` | `src/glean/sinks/registry.py` | `sinks/telegram.py` |
| Search Backend | `async search(query, *, http, limit)` | `@register_backend("name")` | `src/glean/search/registry.py` | `search/searxng.py` |

**To add a plugin: write the file, add an import to `_import_builtins()` in the matching registry — that's the only wiring.** Constructor kwargs come straight from the YAML spec minus the `type`/`provider` key, so the signature *is* the user-facing API.

### Item flow contract

`Item` (`sources/base.py`) is a frozen, slotted dataclass. Sources fill the first cluster (`canonical_url`, `title`, `body`, `source_type`, `source_name`, `published_at`, `score`, `raw`). Pipeline stages fill the second cluster (`llm_summary`, `relevance`, `structured`). Stages produce new `Item` instances via `dataclasses.replace()` — items are never mutated. `canonical_url` is the dedup key (sha256'd); when empty, the store hashes `title + body[:512]`.

### State (`state/store.py`)

aiosqlite plus yoyo SQL migrations in `src/glean/state/migrations/*.sql`. App tables: `seen_items` (dedup + sent tracking), `feed_runs` (per-feed counters + bootstrap flag + alert_active), `etag_cache` (HTTP cache for ETag/Last-Modified honoring sources). On open, applies pending migrations before opening the async connection, then sets `PRAGMA journal_mode=WAL`, `secure_delete=ON`, `foreign_keys=ON`, `trusted_schema=OFF`. `record_success` returns a `recovery` boolean — true means an alert just got cleared, triggers a "recovered" ops message.

### Config (`config/`)

`config/schema.py` is Pydantic v2. `Defaults` + per-`FeedConfig` overrides; the `feed.effective_*(defaults)` methods do the merge — **always call these, never read the raw field**. `StageSpec` accepts both bare strings (`- dedup`) and single-key mappings (`- summarize: { prompt: ... }`); `StageSpec.from_raw` normalizes. `config/loader.py` does YAML load + `${ENV_VAR}` interpolation. `config/schedule.py` parses friendly schedule strings (`every 1h`, `daily 09:00`, `@hourly`, raw 5-field cron) into `IntervalSchedule | CronSchedule`.

LLM precedence: **Skill LLM > Source LLM > Feed LLM > Defaults LLM**.

### Failure model

Transient HTTP/LLM 429s and 5xxs retry within a tick with bounded backoff. Failures escaping the tick increment `consecutive_failures`; at `failure.alert_after` (default 3) the ops chat gets one alert message and `alert_active=1`. Next success clears the flag and posts a recovery message. **No retries between ticks** — the next scheduled run is the retry.

### Security boundaries (added in v1.2.0)

- **`src/glean/security/ssrf.py::validate_url(url, *, allow_private=False)`** — call before any outbound HTTP fetch. Blocks RFC1918/link-local/loopback/cloud-metadata. Use `allow_private=True` for internal Docker hostnames (`ollama:11434`, `searxng:8080`).
- **`src/glean/security/ssrf_transport.SSRFGuardedTransport`** — httpx transport that re-validates on every request to defeat DNS rebinding. Wire into all `httpx.AsyncClient` instances.
- **`src/glean/security/scrub.scrub(text)`** — strip `sk-…`, `Bearer …`, `token=…`, Telegram `/bot…/` patterns from any text headed to logs, ops alerts, or SSE events.
- **`src/glean/llm/output_filter.filter_llm_output()`** — apply to summarize/digest output before passing downstream (catches "ignore previous instructions"-style injections).
- **`src/glean/sinks/escape.py`** — `escape_discord` / `escape_slack` / `safe_url` for sink payloads. `safe_url` drops anything that isn't `http://` or `https://`.
- All scraped content goes into LLM prompts wrapped in `<UNTRUSTED_CONTENT>…</UNTRUSTED_CONTENT>` tags via `llm/common.py::item_as_prompt_context`. System prompts include `INJECTION_GUARD_SYSTEM_PROMPT`.

## Conventions

- **Every Python file starts with** `from __future__ import annotations`.
- **Dataclasses use** `frozen=True, slots=True` for immutability + performance.
- **Pydantic models use** `ConfigDict(extra="forbid")`.
- **Logging** via `glean.logging.get_logger(__name__)` (structlog) — key=value in dev, JSON when `LOG_FORMAT=json`. Never log secrets directly; pass through `scrub()` first.
- **All I/O is async** — `httpx.AsyncClient` for HTTP, `aiosqlite` for SQLite, `ollama.AsyncClient` for Ollama.
- **TYPE_CHECKING guard** — heavy imports used only for type hints go behind `if TYPE_CHECKING:`. **Exception:** if `cast()` references the type at runtime, do a runtime import (CodeQL flags TYPE_CHECKING-only imports as unused when used in string-form casts).
- **Use `pass`, not bare `...`** in protocol stubs and empty bodies — CodeQL `py/empty-statement` blocks merges otherwise.
- **Empty `except: pass` needs an inline comment** explaining why — CodeQL `py/empty-except` blocks merges otherwise.
- **Ruff config** — line length 100, py3.12, permits asserts (`S101` ignored), permits many kwargs (`PLR0913`). Tests ignore `S` and `PLR2004`/`PLC0415`. Late imports allowed in registry modules and CLI.
- **mypy** runs strict.
- **Feed names** must match `^[a-z0-9][a-z0-9._-]*$`.

### Testing patterns

- `pytest-asyncio` with `asyncio_mode = "auto"` — async tests work without a decorator.
- Network mocked with `respx` (already a dev dep).
- Tests register `FakeSource` / `FakeLLM` via the same `@register_*` decorators as real plugins.
- Autouse fixture in `tests/conftest.py` strips secret env vars before every test.
- `write_yaml` fixture creates temp config files; `tmp_db` fixture provides isolated DB.
- E2E suite (`tests/e2e/`) is gated by `pytest.mark.e2e` and excluded by default `addopts = "-m 'not e2e'"`. Conftest spins up `docker-compose.e2e.yml` automatically.
- Playwright UI suite (`ui/e2e/`) starts a dedicated FastAPI test server (`ui/e2e/_server.py`) with `GLEAN_DISABLE_AUTH=1` and `GLEAN_TEST_MODE=1` (which exposes `/api/v1/test/reset`).
- Coverage gates: project ≥80%, patch ≥70%. Codecov posts on PRs.

### Adding a plugin

1. Create the file in `sources/`, `llm/`, `sinks/`, or `search/`.
2. Implement the protocol, decorate with `@register_*`.
3. Add the import to `_import_builtins()` in the matching `registry.py`.
4. Add a unit test (mock network with `respx`).
5. For network sources/sinks: validate URLs via `glean.security.ssrf.validate_url`.
6. Add a snippet to `feeds.example.yaml` and a row in the relevant README table / `docs/plugins/*.md`.

## Repo & workflow

- **Branch naming:** `feat/<slug>`, `fix/<slug>`, `docs/<slug>`, `chore/<slug>`. Squash-merge only — PR title becomes the commit message.
- **Commit trailer:** `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>` on agent-authored commits.
- **Branch protection on `main`** is strict: 11 required checks, `enforce_admins: true`, `required_conversation_resolution: true`. **Never use `--admin`** on `gh pr merge`. Use `gh pr merge <PR> --auto --squash --delete-branch` and let CI gate.
- **CodeQL review threads block merges.** When CodeQL flags a finding, fix the code, then resolve the review thread via GraphQL `resolveReviewThread` mutation (the alert auto-closes when the underlying SARIF result disappears, but the thread doesn't auto-resolve).
- **`README.md` MUST stay out of `.dockerignore`** — hatchling reads it from `pyproject.toml`. Putting it in `.dockerignore` breaks the image build with a confusing cache-key error.
- **No secrets in code or YAML.** `feeds.yaml` is committable; secrets live in `.env` (gitignored) and are referenced via `${VAR}` in `feeds.yaml`. Push protection is on at the repo level. gitleaks runs in CI.
- **EMU gotcha:** if you have multiple `gh auth` accounts, the active EMU account may not be able to create PRs / close PRs / update branches against this personal repo. Use `gh auth switch --user jaypetez` first.
- **Releases:** tag `vX.Y.Z` → `release.yml` publishes multi-arch image to `ghcr.io/jaypetez/glean` (cosign-signed by digest, SBOM attached) plus standalone binaries (linux x86_64/arm64, macos arm64, windows x86_64) and `.deb`/`.rpm`/`.apk` packages.

## Operational defaults

- Bootstrap is `skip-and-mark` by default — first run silently indexes everything; only items appearing on subsequent runs get sent. Override per-feed with `bootstrap: send-last-N` or `bootstrap: send-all`.
- Rendering caps at 10 items per digest; overflow collapsed to a one-liner.
- HTML parse mode by default; `link_preview: false`.
- API server on `:9090`; `GET /healthz` (unauth), `GET /api/v1/initialize` returns `{version, auth_disabled}` (the API key is logged to stderr **once on first creation** as `GLEAN_INITIAL_API_KEY=…`; bootstrap by `docker logs glean | grep GLEAN_INITIAL_API_KEY` or set `GLEAN_API_KEY` env).
- TZ from `$TZ` env var (defaults UTC) — affects `daily HH:MM` schedules.
- Per-feed `max_llm_calls_per_run` caps cost on paid LLMs (default unlimited for back-compat).
