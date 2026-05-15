---
title: "Environment Variables — glean Configuration"
description: Environment variables for auth, state paths, Telegram, LLM providers, and search backends.
---

# Environment Variables

Glean reads configuration from `feeds.yaml` first, then from environment variables where noted. Keep secrets in `.env` and reference them from YAML with `${VAR}` interpolation.

## Core

| Variable | Default | Description |
|----------|---------|-------------|
| `GLEAN_CONFIG` | `/etc/glean/feeds.yaml` | Path to the active feed configuration file. |
| `GLEAN_DB` | `/data/state.db` | SQLite state database path used by the CLI and daemon. |
| `HEALTH_PORT` | `9090` | Port for the API, Web UI, and `/healthz` endpoint. |
| `LOG_LEVEL` | `INFO` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |
| `LOG_FORMAT` | text | Set to `json` for JSON structured logs. |
| `TZ` | `UTC` | IANA timezone used for friendly schedules such as `daily 09:00`. |

## API auth

| Variable | Default | Description |
|----------|---------|-------------|
| `GLEAN_API_KEY` | unset | Fixed API key for `X-Glean-Api-Key`; when unset, Glean auto-generates and persists a verifier. |
| `GLEAN_DISABLE_AUTH` | unset / false | Set to `1`, `true`, or `yes` to bypass API auth for trusted local test deployments only. |

## State paths

| Variable | Default | Description |
|----------|---------|-------------|
| `GLEAN_DB_ROOT` | `/data` | Comma-separated allowlist of directories where SQLite state databases may live. |
| `GLEAN_FILE_SINK_ROOTS` | `/data,/tmp/glean` | Comma-separated allowlist of directories where the file sink may write. |
| `GLEAN_TEST_MODE` | unset / false | Enables test-only API reset endpoints; never set in production. |

## Telegram

| Variable | Default | Description |
|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | unset | Bot token from BotFather, used by the Telegram sink when YAML does not specify `token`. |
| `TELEGRAM_BASE_URL` | Telegram Bot API | Optional Telegram Bot API base URL for self-hosted Bot API servers or tests. |

## LLM providers

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_BASE_URL` | `http://ollama:11434` | Conventional value to interpolate into `llm.base_url` for Ollama deployments. |
| `OPENAI_API_KEY` | unset | OpenAI API key, required when using the `openai` provider unless passed in YAML. |
| `ANTHROPIC_API_KEY` | unset | Anthropic API key, required when using the `anthropic` provider unless passed in YAML. |

## Search backends

| Variable | Default | Description |
|----------|---------|-------------|
| `BRAVE_API_KEY` | unset | Brave Search API key for the `brave` backend. |
| `TAVILY_API_KEY` | unset | Tavily API key for the `tavily` backend. |
| `SERPER_API_KEY` | unset | Serper.dev API key for the `serper` backend. |
| `EXA_API_KEY` | unset | Exa API key for the `exa` backend. |

## SearXNG

| Variable | Default | Description |
|----------|---------|-------------|
| `SEARXNG_SECRET` | unset | Secret key for the optional bundled SearXNG service; generate a 32+ hex-character value. |
| `SEARXNG_URL` | unset | Base URL for a self-hosted SearXNG instance used by the `searxng` backend. |
