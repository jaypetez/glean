---
title: "feeds.yaml Reference — glean Configuration"
description: Complete reference for source types, pipeline stages, sinks, schedules, and feed options.
---

# feeds.yaml Reference

!!! info
    [Download the JSON Schema](../reference/feeds-schema.json) for IDE validation and AI agent consumption.

## Source types

| Type      | Args                                                            |
|-----------|-----------------------------------------------------------------|
| `rss`     | `url`, `max_response_bytes` (default `10485760`, 10 MiB)        |
| `scraper` | `urls: [list of article URLs]`, `max_response_bytes` (default `10485760`, 10 MiB) |
| `hn`      | `query`, `tags` (default `story`), `min_points`, `window_hours` |
| `reddit`  | `subreddit`, `sort` (`top`/`new`/`hot`), `timeframe`, `limit`   |
| `search`  | `query`, `engine`, `limit`, plus engine-specific kwargs (see below) |

RSS and scraper sources stream HTTP responses and abort once the body exceeds
`max_response_bytes`, preventing unbounded memory use from oversized feeds or
pages. Set a lower per-source cap when fetching from untrusted endpoints.

### Per-source LLM

Any source spec accepts an optional `llm:` field. This overrides the feed/default
LLM for items fetched from that source, so one feed can mix local and premium
models by source. See the [per-source dispatch how-to](../how-to/llm/per-source.md)
or the [per-source LLM reference](./per-source-llm.md).

### Search backends

The `search` source delegates to a pluggable backend. Each backend has its
own constructor kwargs which become YAML fields. Six backends ship
out-of-the-box; see [Authoring Search Backends](../plugins/search.md) for how
to add more.

#### `searxng` (self-hosted, free)

| Field | Required | Description |
|-------|----------|-------------|
| `base_url` | yes (or `SEARXNG_URL` env) | URL of your SearXNG instance |
| `categories` | no | Comma-separated SearXNG categories (default `general`) |
| `time_range` | no | `day`, `week`, `month`, or `year` |
| `safesearch` | no | `0` (off), `1` (moderate), `2` (strict) — default `0` |

#### `brave`

| Field | Required | Description |
|-------|----------|-------------|
| `api_key` | no (defaults to `BRAVE_API_KEY` env) | Brave Search API key |

#### `tavily`

| Field | Required | Description |
|-------|----------|-------------|
| `api_key` | no (defaults to `TAVILY_API_KEY` env) | Tavily API key |
| `search_depth` | no | `basic` (default) or `advanced` (fetches full pages) |

#### `serper`

| Field | Required | Description |
|-------|----------|-------------|
| `api_key` | no (defaults to `SERPER_API_KEY` env) | Serper.dev API key |
| `country` | no | Two-letter country code (default `us`) |

#### `exa`

| Field | Required | Description |
|-------|----------|-------------|
| `api_key` | no (defaults to `EXA_API_KEY` env) | Exa.ai API key |
| `type` | no | `neural`, `keyword`, or `auto` (default) |
| `include_text` | no | `true` to include full page text (large payloads — default `false`) |

#### `mwmbl` (free, no API key)

| Field | Required | Description |
|-------|----------|-------------|
| `base_url` | no | Override the API host (default `https://api.mwmbl.org`) |

#### Example: multi-backend feed

```yaml
feeds:
  - name: ai-research
    schedule: "every 1h"
    chat_id: ${TELEGRAM_CHAT_AI}
    sources:
      - type: search
        query: "LLM evaluation methods"
        engine: searxng
        base_url: http://searxng:8080
        time_range: week
      - type: search
        query: "transformer architecture"
        engine: brave
      - type: search
        query: "embedding models 2025"
        engine: exa
    pipeline:
      - dedup
      - rank: { prompt: "0-1 score: relevance to ML researchers", min_relevance: 0.4 }
      - summarize: { prompt: "One-sentence summary." }
      - digest: { intro: "🧠 AI research" }
```

## LLM providers

Configure the default provider under `defaults.llm`, override it per feed with
`feeds[].llm`, or override it per source with `sources[].llm`.

| Field | Required | Description |
|-------|----------|-------------|
| `provider` | no | `ollama` by default. Built-ins: `ollama`, `openai`, `anthropic`. |
| `model` | no | Provider model name. Defaults to `qwen2.5:7b`. |
| `base_url` | no | Provider API base URL override. Most users only set this for non-bundled Ollama or compatible gateways. |
| `api_key` | no | Inline API key. Prefer environment variables for secrets. |
| `timeout_s` | no | LLM request timeout in seconds. Defaults to `60`. |

### Built-in providers

| Provider | Default model | API key |
|----------|---------------|---------|
| `ollama` | `qwen2.5:7b` | None. Uses bundled `http://ollama:11434` unless `base_url` is set. |
| `openai` | `gpt-4o-mini` | `OPENAI_API_KEY` env var, unless `api_key` is set. |
| `anthropic` | `claude-haiku-4-5` | `ANTHROPIC_API_KEY` env var, unless `api_key` is set. |

```yaml
defaults:
  llm:
    provider: ollama
    model: qwen2.5:7b

feeds:
  - name: paid-summary
    llm:
      provider: openai
      model: gpt-4o-mini
```

See [Ollama](../how-to/llm/ollama.md), [OpenAI](../how-to/llm/openai.md),
and [Anthropic](../how-to/llm/anthropic.md) for setup steps.

## Pipeline stages

| Stage       | Effect                                                       |
|-------------|--------------------------------------------------------------|
| `dedup`     | Drop already-seen items (by canonical URL hash).             |
| `rank`      | LLM scores each item; drops below `min_relevance` (0..1).   |
| `summarize` | LLM writes a 1-line summary, attached to each item.         |
| `apply_skill` | Run a structured extraction skill on each item; attaches result to `Item.structured` and copies a `summary`/`one_liner`/`tldr` field into `llm_summary`. See [Skills](./skills.md). |
| `digest`    | Sets the digest header. Optionally LLM-synthesized.         |

## LLM call budget

Set `max_llm_calls_per_run` to cap total LLM calls made by one feed run across
`rank`, `summarize`, `apply_skill`, and LLM-generated `digest` stages. With
no default or feed cap configured, runs are unlimited for backwards
compatibility. Use a budget such as `50` for feeds that use paid providers.

```yaml
defaults:
  max_llm_calls_per_run: 50   # optional global default

feeds:
  - name: ai-news
    max_llm_calls_per_run: 25 # optional per-feed override
```

When the budget is exhausted, glean logs `llm_budget_capped` once for that run.
Items that skip an LLM stage still continue through the pipeline; skipped
summaries are left blank. If the budget is exhausted during `rank`, unranked
items continue after ranked items, so set the cap high enough when ranking is
your primary quality filter.

## Sinks

Each feed delivers its digest to one or more **sinks**. Configure them with the
`sinks:` list at the feed level:

```yaml
feeds:
  - name: ai-news
    schedule: "every 1h"
    sinks:
      - type: telegram
        chat_id: ${TELEGRAM_CHAT_AI}
      - type: discord
        webhook_url: ${DISCORD_WEBHOOK_AI}
        required: false       # failure here doesn't trigger ops alerts
      - type: file
        path: /data/glean-archive.jsonl
        format: jsonl
      - type: dashboard
        keep_last_n: 50
    sources: [...]
    pipeline: [...]
```

### Backwards compatibility

The legacy single-sink syntax still works:

```yaml
feeds:
  - name: ai-news
    chat_id: ${TELEGRAM_CHAT_AI}    # shorthand for sinks: [{type: telegram, chat_id: ...}]
    sources: [...]
    pipeline: [...]
```

### Sink reference

#### `telegram`

| Field | Required | Description |
|-------|----------|-------------|
| `chat_id` | yes | Chat ID (negative for groups, positive for users) |
| `token` | no | Bot token (defaults to `TELEGRAM_BOT_TOKEN` env var) |
| `base_url` | no | Override Telegram API base URL (for self-hosted Bot API or testing). Defaults to `TELEGRAM_BASE_URL` env var when set. |
| `required` | no | Default `true` |

#### `discord`

| Field | Required | Description |
|-------|----------|-------------|
| `webhook_url` | yes | Discord webhook URL. Must match `https://discord.com/api/webhooks/<digits>/<token>` where `<token>` contains only letters, digits, `_`, `.`, or `-`. |
| `username` | no | Override webhook username |
| `avatar_url` | no | Override webhook avatar. Must be an SSRF-safe HTTP(S) URL. |
| `required` | no | Default `true` |

#### `slack`

| Field | Required | Description |
|-------|----------|-------------|
| `webhook_url` | yes | Slack incoming webhook URL. Must match `https://hooks.slack.com/services/T.../B.../<token>` with uppercase alphanumeric `T`/`B` segments and an alphanumeric token. |
| `channel` | no | Override default channel (e.g., `#news`) |
| `username` | no | Override webhook username |
| `icon_emoji` | no | Override webhook icon (e.g., `:robot_face:`) |
| `required` | no | Default `true` |

#### `ntfy`

| Field | Required | Description |
|-------|----------|-------------|
| `topic` | yes | ntfy topic name. Must be 1-64 characters: letters, digits, `_`, or `-`. |
| `base_url` | no | Defaults to `https://ntfy.sh` |
| `token` | no | Bearer token for private servers |
| `priority` | no | Message priority (1-5) |
| `tags` | no | List of tag strings |
| `required` | no | Default `true` |

#### `webhook`

| Field | Required | Description |
|-------|----------|-------------|
| `url` | yes | Target URL |
| `method` | no | HTTP method (default `POST`) |
| `headers` | no | Additional headers as a dict |
| `auth_bearer` | no | Bearer token (added as `Authorization` header) |
| `auth_basic` | no | `[username, password]` for basic auth |
| `required` | no | Default `true` |

The webhook payload is JSON:

```json
{
  "feed": "ai-news",
  "intro": "AI news this hour",
  "messages": ["..."],
  "items": [{"title": "...", "url": "...", "summary": "...", "source_type": "rss", ...}]
}
```

#### `file`

| Field | Required | Description |
|-------|----------|-------------|
| `path` | yes | Local file path under an allowed root (parent dirs created automatically) |
| `format` | no | One of `text`, `jsonl`, `markdown` (default `text`) |
| `required` | no | Default `true` |

File sink paths must resolve under `/data` or `/tmp/glean` by default and may not exceed 10 path segments below the allowed root. Set `GLEAN_FILE_SINK_ROOTS` to a comma-separated list of allowed root directories to customize this allowlist (for example, `GLEAN_FILE_SINK_ROOTS=/data,/archive`). On Windows, set `GLEAN_FILE_SINK_ROOTS` explicitly because the defaults are container/Linux paths. Ensure allowed roots exist and are writable by the glean process.

#### `dashboard`

| Field | Required | Description |
|-------|----------|-------------|
| `keep_last_n` | no | Per-feed retention cap for stored digest fragments. Default `50`; oldest entries are evicted first. |
| `required` | no | Default `true` |

The dashboard sink stores rendered digest fragments in SQLite for the built-in web UI and digest APIs. Retention is enforced per feed in the same transaction as the insert, so each feed keeps only its most recent `keep_last_n` fragments.

### Multiple sinks (fan-out)

When a feed has multiple sinks, glean sends to all of them in parallel using
`asyncio.gather`. Failure semantics:

- **Required sink fails** → counts as a feed failure (increments
  `consecutive_failures`, may trigger ops alert)
- **Optional sink fails** (`required: false`) → logged as warning only

This lets you mirror outputs (Telegram + Discord) where one is primary and
one is best-effort, or write archive files alongside live notifications.

## Schedule syntax

| String              | Meaning                                |
|---------------------|----------------------------------------|
| `every 30s`         | Every 30 seconds                       |
| `every 15m`         | Every 15 minutes                       |
| `every 1h`          | Every hour                             |
| `daily 09:00`       | Every day at 09:00 (`$TZ`)             |
| `@hourly`, `@daily` | Cron presets                           |
| `0 */2 * * *`       | Any 5-field cron expression            |

## LLM configuration

```yaml
llm:
  provider: ollama          # ollama | anthropic | openai
  model: qwen2.5:7b
  base_url: http://ollama:11434
  timeout_s: 60.0
```

For paid LLMs, also set `max_llm_calls_per_run` on `defaults` or individual
feeds to prevent one large tick from making unbounded model calls.

## Render configuration

```yaml
render:
  style: html               # html | markdown_v2 | plain
  link_preview: false
  max_items: 10              # 1..50
```

## Failure configuration

```yaml
failure:
  alert_after: 3             # consecutive failures before ops-chat alert
  ops_chat_id: ${TELEGRAM_OPS_CHAT_ID}
```
