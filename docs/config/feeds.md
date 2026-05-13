# feeds.yaml Reference

## Source types

| Type      | Args                                                            |
|-----------|-----------------------------------------------------------------|
| `rss`     | `url`                                                           |
| `scraper` | `urls: [list of article URLs]`                                  |
| `hn`      | `query`, `tags` (default `story`), `min_points`, `window_hours` |
| `reddit`  | `subreddit`, `sort` (`top`/`new`/`hot`), `timeframe`, `limit`   |
| `search`  | `query`, `engine` (`brave`/`tavily`/`searxng`), `limit`         |

## Pipeline stages

| Stage       | Effect                                                       |
|-------------|--------------------------------------------------------------|
| `dedup`     | Drop already-seen items (by canonical URL hash).             |
| `rank`      | LLM scores each item; drops below `min_relevance` (0..1).   |
| `summarize` | LLM writes a 1-line summary, attached to each item.         |
| `digest`    | Sets the digest header. Optionally LLM-synthesized.         |

## Sink configuration

`chat_id` is backwards-compatible shorthand for a Telegram sink. Use `sinks:` when a feed should declare output destinations explicitly or fan out to multiple sinks.

```yaml
chat_id: ${TELEGRAM_CHAT_AI}
# equivalent to:
sinks:
  - type: telegram
    chat_id: ${TELEGRAM_CHAT_AI}
```

<<<<<<< HEAD
Built-in sink types:

| Type       | Required args | Optional args |
|------------|---------------|---------------|
| `telegram` | `chat_id` | `token`, `base_url`, `required` |
| `discord`  | `webhook_url` | `username`, `avatar_url`, `timeout_s`, `required` |
| `ntfy`     | `topic` | `base_url`, `token`, `priority`, `tags`, `timeout_s`, `required` |
| `slack`    | `webhook_url` | `channel`, `username`, `icon_emoji`, `timeout_s`, `required` |

The `base_url` for the `telegram` sink overrides the Telegram Bot API endpoint (defaults to `TELEGRAM_BASE_URL` env var if not set). Useful for pointing at a self-hosted Bot API or a mock server during testing.

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
