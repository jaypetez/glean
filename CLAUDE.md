# CLAUDE.md

@docs/plugins/source.md
@docs/plugins/llm.md
@docs/plugins/sink.md
@docs/plugins/search.md
@docs/operations/security.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# dev setup (Python 3.12+)
uv venv
. .venv/Scripts/activate          # Windows; macOS/Linux: . .venv/bin/activate
uv pip install -e ".[dev]"

# the three checks CI gates on — run all before pushing
ruff check src tests
mypy src                          # strict mode, will catch real bugs
pytest -q

# single test
pytest tests/test_runner.py -q
pytest tests/test_runner.py::test_bootstrap_skip -q

# run the daemon / CLI without the container
glean validate-config -c feeds.example.yaml
glean test-feed <feed-name> -c feeds.example.yaml   # dry-run, no Telegram, no state writes
glean test-feed <feed-name> --send                   # actually sends
glean send-now <feed-name>                           # off-schedule single run
glean list-feeds
glean run                                            # the daemon (container entrypoint)

# docker
docker compose up -d
docker exec -it glean-ollama ollama pull qwen2.5:7b   # first time
docker exec -it glean glean test-feed <feed-name>
```

`pyproject.toml` is the single source of truth for ruff, mypy, and pytest config.
`mypy` is **strict** (`disallow_untyped_defs`, `warn_return_any`, `warn_unused_ignores`); CI fails on any new error.

## Standardized dev loop

```bash
make dev      # one-time setup (Python + UI deps)
make check    # ruff + mypy + pytest — run before every commit
make test     # unit tests only
make e2e      # docker compose e2e
make ui-test  # playwright UI e2e
```

Pre-commit hooks: `uv run pre-commit install` once, then ruff + mypy + a few hygiene checks run on `git commit`.

On Windows, install `make` via Chocolatey (`choco install make`), use WSL, or run the underlying commands directly.

## Architecture

The daemon is **one container, many feeds**. A feed is `sources → LLM pipeline → Telegram chat → schedule`, all declared in YAML. The same process runs N independent feeds with N independent schedules.

### Per-feed runtime flow (`src/glean/pipeline/engine.py::Runner.run_feed`)

```
APScheduler tick
  → fetch from each source (errors per source are warnings, not feed failures)
  → bootstrap branch: if feed is unbootstrapped and mode is skip-and-mark,
    insert all current items into seen_items with sent=1, do NOT send, mark bootstrapped
  → dedup against seen_items (state-backed)
  → for each stage in feed.pipeline (declared in YAML):
        dedup    — within-batch hash dedup
        rank     — LLM scores each item, drop below min_relevance
        summarize— LLM writes per-item summary, attached as Item.llm_summary
        digest   — sets intro/header text (optionally LLM-generated)
  → cap to render.max_items, overflow becomes one "…and N more" line
  → render to Telegram HTML, split at 4096 chars
  → send → mark_seen(sent=1) → record_success
  → on failure: record_failure increments consecutive_failures; alert ops_chat once threshold hit
```

The pipeline stages are reorderable in YAML. `summarize` before `rank` is legal (lets the LLM rank its own summary — more LLM calls, better recall).

### Plugin registries — how new sources / providers get wired

Two parallel registry patterns, same shape:

- `src/glean/sources/registry.py` — `@register_source("type-name")`; `build_source(spec_dict)` instantiates from YAML
- `src/glean/llm/registry.py` — `@register_provider("provider-name")`; `build_provider(spec_dict)` likewise

Both registries call `_import_builtins()` at module load to force decorator side-effects. **To add a new source/provider, write the file and add the import to `_import_builtins()`** in the matching registry — that's the only wiring. Constructor kwargs come straight from the YAML spec minus the `type`/`provider` key, so the signature *is* the user-facing API.

See `docs/plugins.md` for examples. Smallest reference implementations: `sources/rss.py` and `llm/ollama_provider.py`.

### Item flow contract

`Item` (`sources/base.py`) is a frozen dataclass. Sources fill the first cluster of fields (`canonical_url`, `title`, `body`, `summary`, `source_type`, `source_name`, `published_at`, `score`, `raw`). Pipeline stages fill the second cluster (`llm_summary`, `relevance`). `canonical_url` is the dedup key (sha256'd); when empty, the store hashes `title + body[:512]` instead.

### State

SQLite via `aiosqlite`, schema migrations in `state/migrations/*.sql`. Three app tables: `seen_items` (dedup + sent tracking), `feed_runs` (per-feed success/failure counters + bootstrap flag), `etag_cache` (HTTP cache for sources like RSS that honor ETag/Last-Modified). `StateStore.open()` applies pending yoyo migrations before opening the async connection and setting PRAGMAs.

`StateStore.record_success` returns a `recovery` boolean — true means `alert_active` was set and just got cleared, which triggers a "recovered" ops message.

## State migrations

Schema lives in `src/glean/state/migrations/*.sql`. To add a column or table:

1. Create `src/glean/state/migrations/NNNN_describe_change.sql` (next sequential number)
2. Add the `-- depends: NNNN_previous` header
3. Tests will pick it up automatically; production picks it up on next `StateStore.open()`

Manual migration: `glean migrate --db /data/state.db`

### Config

`config/schema.py` — pydantic v2 models. `Defaults` + per-`FeedConfig` overrides; the `feed.effective_*(defaults)` methods do the merge — always call these, never read the raw field. `StageSpec` accepts both bare strings (`- dedup`) and single-key mappings (`- summarize: { prompt: ... }`); `StageSpec.from_raw` normalizes.

`config/loader.py` does YAML load + `${ENV_VAR}` interpolation. `config/schedule.py` parses the friendly schedule strings (`every 1h`, `daily 09:00`, `@hourly`, raw 5-field cron).

### Failure model

Transient HTTP/LLM 429s and 5xxs are retried *within a tick* with bounded backoff. A failure that escapes the tick increments `consecutive_failures`; at `failure.alert_after` (default 3) the ops chat gets one message and `alert_active=1`. Next success clears the flag and posts a recovery message. No retries between ticks — the next scheduled run is the retry.

### Operational defaults

- Bootstrap is `skip-and-mark` by default — first run silently indexes everything; only items appearing on subsequent runs get sent. Override per-feed with `bootstrap: send-last-N` or `bootstrap: send-all`.
- Rendering caps at 10 items per digest; overflow collapsed to a one-liner.
- `link_preview: false` by default; HTML parse mode by default.
- Health endpoint on `:9090/healthz`.
- TZ from `$TZ` env var (defaults UTC) — affects `daily HH:MM` schedules.

## Repo & workflow

- **MIT license**, public repo, single maintainer (`@jaypetez`).
- **Branch protection on `main`**: required check `Lint, type-check, test`, 1 approving review required, CODEOWNERS-gated, linear history, no force-push, no deletion. Admins bypass review (so you can self-merge), but **do not push directly to main** — always go through a PR.
- **Squash-merge only**; the PR title becomes the commit message.
- **Image** at `ghcr.io/jaypetez/glean` — multi-arch (amd64+arm64), built from `Dockerfile` (`python:3.14-slim` base). Tags: `latest` + `sha-<short>` on each push to main; full semver on `v*.*.*` tag (release.yml).
- **Dockerfile gotcha**: hatchling reads `readme = "README.md"` from pyproject.toml, so `README.md` MUST stay in the build context (it's COPYed in the builder stage and NOT in `.dockerignore`). If you re-add it to `.dockerignore`, the image build will fail with a confusing `failed to compute cache key` error.
- **No secrets in code or YAML.** `feeds.yaml` is committable; secrets live in `.env` (gitignored) and are referenced via `${VAR}` in `feeds.yaml`. Push protection is on at the repo level.

## Test mode

`GLEAN_TEST_MODE=1` enables `POST /api/v1/test/reset?fixture=default|empty` — wipes the DB and re-seeds the test fixture. **Only registered when this env is set; never available in production.** Used by `ui/e2e/_server.py` for the Playwright suite.

`GLEAN_DISABLE_AUTH=1` bypasses the API key check entirely. Emits a startup WARNING. Used by the e2e harness; never set in production.

## API key bootstrap

On first boot the API key is auto-generated and logged ONCE to stderr at WARNING level:

```
GLEAN_INITIAL_API_KEY=<32-char key>
```

Operators retrieve it via `docker logs glean | grep GLEAN_INITIAL_API_KEY`. Subsequent restarts persist only the verifier hash on disk (`/data/api_key`, mode 0o600); the cleartext key is NOT recoverable. Set `GLEAN_API_KEY=<key>` env to skip auto-generation entirely.

## Linting & autofix

`uv run ruff check --fix src tests` auto-fixes most style issues. Always run `mypy src` BEFORE `ruff --fix` — mypy may surface refactors that ruff then wants to simplify.
