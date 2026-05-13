# feeds.yaml Reference

## Source types

| Type      | Args                                                            |
|-----------|-----------------------------------------------------------------|
| `rss`     | `url`                                                           |
| `scraper` | `urls: [list of article URLs]`                                  |
| `hn`      | `query`, `tags` (default `story`), `min_points`, `window_hours` |
| `reddit`  | `subreddit`, `sort` (`top`/`new`/`hot`), `timeframe`, `limit`   |
| `search`  | `query`, `engine`, `limit`, plus engine-specific kwargs (see below) |

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

## Pipeline stages

| Stage       | Effect                                                       |
|-------------|--------------------------------------------------------------|
| `dedup`     | Drop already-seen items (by canonical URL hash).             |
| `rank`      | LLM scores each item; drops below `min_relevance` (0..1).   |
| `summarize` | LLM writes a 1-line summary, attached to each item.         |
| `digest`    | Sets the digest header. Optionally LLM-synthesized.         |

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
| `webhook_url` | yes | Discord webhook URL |
| `username` | no | Override webhook username |
| `avatar_url` | no | Override webhook avatar |
| `required` | no | Default `true` |

#### `slack`

| Field | Required | Description |
|-------|----------|-------------|
| `webhook_url` | yes | Slack incoming webhook URL |
| `channel` | no | Override default channel (e.g., `#news`) |
| `username` | no | Override webhook username |
| `icon_emoji` | no | Override webhook icon (e.g., `:robot_face:`) |
| `required` | no | Default `true` |

#### `ntfy`

| Field | Required | Description |
|-------|----------|-------------|
| `topic` | yes | ntfy topic name |
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
| `path` | yes | Local file path (parent dirs created automatically) |
| `format` | no | One of `text`, `jsonl`, `markdown` (default `text`) |
| `required` | no | Default `true` |

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
