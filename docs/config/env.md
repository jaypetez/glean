# Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes | Bot token from @BotFather |
| `TELEGRAM_CHAT_*` | Per feed | Chat IDs referenced in feeds.yaml |
| `ANTHROPIC_API_KEY` | If used | Anthropic provider API key |
| `OPENAI_API_KEY` | If used | OpenAI provider API key |
| `BRAVE_API_KEY` | If used | Brave Search API key |
| `TAVILY_API_KEY` | If used | Tavily Search API key |
| `SEARXNG_SECRET` | If using SearXNG | Secret key for the optional SearXNG service |
| `TZ` | No | Timezone (default: `UTC`) |
| `LOG_LEVEL` | No | Logging level (default: `INFO`) |
| `LOG_FORMAT` | No | Set to `json` for JSON logs |
| `GLEAN_CONFIG` | No | Config path (default: `/etc/glean/feeds.yaml`) |
| `GLEAN_DB` | No | DB path (default: `/data/state.db`) |
| `GLEAN_DB_ROOT` | No | Comma-separated allowed DB root paths (default: `/data`) |
| `HEALTH_PORT` | No | Health endpoint port (default: `9090`) |
