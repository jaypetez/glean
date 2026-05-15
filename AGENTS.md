# AGENTS.md

> Read by GitHub Copilot (agent mode), OpenAI Codex, and other AI coding agents that follow the AGENTS.md convention.
> Detailed guidance lives in **CLAUDE.md** (Claude Code) and **`.github/copilot-instructions.md`** (Copilot chat)  this file is a quick orientation.

## What this repo is

`glean` is an async Python 3.12 daemon that aggregates content from RSS / web scraping / search backends, summarizes it via pluggable LLM providers (Ollama / OpenAI / Anthropic), and posts digests to Telegram / Discord / Slack / ntfy / webhook / file sinks. A built-in FastAPI server + Svelte 5 SPA at port 9090 manages it. Self-hosted, single Docker container.

## Quick start

```bash
uv sync --locked --all-extras
uv run ruff check src tests   # lint
uv run mypy src               # type-check (strict)
uv run pytest -q              # unit tests (e2e excluded by default)
```

The full validation loop CI runs is also wrapped in `make check` (after PR3 lands).

## Architecture in 3 sentences

One container, one process, one asyncio event loop hosting: APScheduler (per-feed ticks) + FastAPI (REST + SSE + SPA) + the pipeline (`Runner.run_feed`). The CLI and API share a service layer (`api_service/`) so they never disagree on truth. Plugins (sources, LLM providers, sinks, search backends) all use the same `@register_*` decorator + `_import_builtins()` registration pattern.

## When you're about to make changes

1. **Read `CLAUDE.md`** for build commands, conventions, and tribal knowledge.
2. **Read `.github/copilot-instructions.md`** for the longer plugin tables and security boundaries.
3. **For specific subsystems** see `docs/`:
   - `docs/plugins/source.md`  adding a Source plugin
   - `docs/plugins/llm.md`  adding an LLM provider
   - `docs/plugins/sink.md`  adding a Sink
   - `docs/plugins/search.md`  adding a Search backend
   - `docs/security.md`  security model + threat model

## Things that will block your PR

- Empty `except: pass` (CodeQL `py/empty-except`)
- Bare `...` in protocol stubs (CodeQL `py/empty-statement`)  use `pass`
- Hardcoded versions of base images in tests (the test asserts SHA digest pinning, not specific versions)
- Mutating an `Item` (always use `dataclasses.replace`)
- Missing `from __future__ import annotations` at the top of new files
- Skipping `validate_url()` on outbound HTTP destinations

## Branch protection on `main`

- 11 required CI checks must pass
- `enforce_admins: true`  no `--admin` bypass
- Squash-merge only  PR title becomes the commit message
- Use `gh pr merge <PR> --auto --squash --delete-branch`

## EMU users

If you have multiple `gh auth` accounts, the active EMU account may not be able to create/close/update PRs against this personal repo. Run `gh auth switch --user jaypetez` first.
