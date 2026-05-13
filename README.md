<h1 align="center">glean</h1>

<p align="center">
  <em>Self-hosted, pluggable personal agent that gleans signal from RSS, scraping, search, and APIs — processes it with any LLM, then fans out scheduled digests to whichever sinks you wire up.</em>
</p>

<p align="center">
  <img src="./assets/glean-hero.svg" alt="glean: pluggable sources flow into a central LLM pipeline (dedup, rank, summarize, digest) which fans out scheduled digests to Telegram, Discord, Slack, ntfy, Webhook, and File sinks" width="100%">
</p>

<p align="center">
  <a href="https://github.com/jaypetez/glean/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/jaypetez/glean/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://github.com/jaypetez/glean/actions/workflows/codeql.yml"><img alt="CodeQL" src="https://github.com/jaypetez/glean/actions/workflows/codeql.yml/badge.svg"></a>
  <a href="https://codecov.io/gh/jaypetez/glean"><img alt="Coverage" src="https://codecov.io/gh/jaypetez/glean/branch/main/graph/badge.svg"></a>
  <a href="./LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-blue.svg"></a>
  <a href="https://www.python.org/downloads/"><img alt="Python 3.12+" src="https://img.shields.io/badge/python-3.12+-3776ab.svg"></a>
  <a href="https://github.com/jaypetez/glean/pkgs/container/glean"><img alt="ghcr.io image" src="https://img.shields.io/badge/ghcr.io-glean-24292f?logo=docker&logoColor=white"></a>
  <a href="https://github.com/jaypetez/glean/discussions"><img alt="Discussions" src="https://img.shields.io/badge/discussions-open-7c3aed.svg"></a>
</p>

`glean` is a small Python daemon that runs as a Docker container. You describe **feeds** in a YAML file — each one is a recipe of `sources → LLM pipeline → sinks → schedule`. It deduplicates, ranks, summarizes, and posts a clean digest. One container, many topics, many sinks.

## Status

**v1.0** — stable core surfaces. Six shipped sinks (Telegram, Discord, Slack, ntfy.sh, Webhook, File), six search backends (SearXNG self-hosted + Brave / Tavily / Serper / Exa / MWMBL), three LLM providers (Ollama, Anthropic, OpenAI), and a four-layer plugin system (Source, Sink, LLM Provider, Search Backend) — all extendable in a single file.

See [DESIGN.md](./DESIGN.md) for the long view.

## Why

The use case that started it: drop the agent in your "AI news" Telegram group, and once an hour it posts a tight 10-item digest summarized by your local Ollama. Add a second feed for security CVEs that runs daily and uses Claude. Add a third for `r/LocalLLaMA` top-of-day. The agent doesn't care what the topic is — sources, prompts, models, sinks are all config.

The longer game: any "periodically pull X, process with an LLM, deliver to Y" workflow — research clipping, deal scraping, job monitoring, GitHub release tracking, on-call digests — should be a few lines of YAML, not a custom script.

## Features

- **Pluggable sources** — RSS/Atom, web scraping, Hacker News, Reddit, web search (SearXNG / Brave / Tavily / Serper / Exa / MWMBL). Add your own in one file. See [`docs/plugins/source.md`](./docs/plugins/source.md).
- **Pluggable sinks** — Telegram, Discord, Slack, ntfy.sh, generic Webhook, File (text/JSONL/markdown). Fan out a single feed to multiple sinks; mark some as `required: false` to swallow non-critical failures. See [`docs/plugins/sink.md`](./docs/plugins/sink.md).
- **Pluggable LLM** — Ollama (default), Anthropic, OpenAI. Per-feed provider/model: local for the noisy feed, Claude for the important one. See [`docs/plugins/llm.md`](./docs/plugins/llm.md).
- **Per-source LLM models** — each source within a feed can use its own LLM. Cheap local model for noisy RSS, Claude Haiku for the curated subreddit, premium Sonnet for the security feed. See [`docs/config/per-source-llm.md`](./docs/config/per-source-llm.md).
- **Reusable structured skills** — define named extraction templates with JSON output schemas, then reference them from any feed. Built-in examples: deal-finder, CVE extractor, paper digest, job posting. See [`docs/config/skills.md`](./docs/config/skills.md).
- **Pluggable web search** — six backends including the self-hosted [SearXNG](./docs/getting-started/search.md) for users who don't want cloud API keys. See [`docs/plugins/search.md`](./docs/plugins/search.md).
- **Per-feed pipeline** — declare stages in YAML: `dedup → rank → summarize → digest`. Reorder freely. Skip stages you don't want.
- **Smart dedup** — SQLite-backed (WAL mode), persists across restarts. New feed? Indexed silently on first tick — no surprise 200-item dump.
- **Friendly schedules** — `every 1h`, `every 15m`, `daily 09:00`, or raw cron.
- **Failure-aware** — exponential backoff in-tick, ops-chat alert after N consecutive failures, auto-clear on recovery. Optional sinks don't trigger alerts.
- **Cross-platform** — runs as a Docker container or a standalone binary. Linux (x86_64 + arm64), macOS (arm64), and Windows (x86_64) builds attached to every release.
- **Hardened release** — multi-arch container (`ghcr.io/jaypetez/glean`), cosign-signed by digest, SBOM generated. `.deb`, `.rpm`, and `.apk` packages produced via nfpm.
- **One container** — `docker compose up`. Ollama is bundled in the compose file; bring your own if you prefer.

## Quickstart (5 minutes)

```bash
git clone https://github.com/jaypetez/glean.git
cd glean

# 1. Get a Telegram bot token from @BotFather, add the bot to a group, get the chat id
#    (one easy way: send a message in the group then visit
#     https://api.telegram.org/bot<TOKEN>/getUpdates )

# 2. Configure
cp .env.example .env                 # fill in TELEGRAM_BOT_TOKEN + chat IDs
cp feeds.example.yaml feeds.yaml     # tweak feeds, prompts, schedules

# 3. Run
docker compose up -d

# 4. Pull an Ollama model the first time
docker exec -it glean-ollama ollama pull qwen2.5:7b

# 5. Sanity-check a feed without sending
docker exec -it glean glean test-feed ai-news-daily
```

Want self-hosted web search too? See [Web search setup](./docs/getting-started/search.md) — uncomment SearXNG in `docker-compose.yml` and you're done in two more commands.

## Configuration

Two files, two responsibilities:

- **`.env`** — secrets (bot tokens, API keys, chat IDs). Never committed.
- **`feeds.yaml`** — feeds, sources, prompts, schedules, sinks. Safe to commit. References `${ENV_VARS}`.

See [`feeds.example.yaml`](./feeds.example.yaml) for a working starter.

### Minimum feed

```yaml
defaults:
  llm:
    provider: ollama
    model: qwen2.5:7b
    base_url: http://ollama:11434

feeds:
  - name: ai-news-daily
    schedule: "every 1h"
    chat_id: ${TELEGRAM_CHAT_AI}
    sources:
      - type: rss
        url: https://simonwillison.net/atom/everything/
    pipeline:
      - dedup
      - summarize:
          prompt: "One-sentence summary."
      - digest:
          intro: "🧠 <b>AI news this hour</b>"
```

### Source types

| Type      | Args                                                            |
|-----------|-----------------------------------------------------------------|
| `rss`     | `url`                                                           |
| `scraper` | `urls: [list of article URLs]`                                  |
| `hn`      | `query`, `tags` (default `story`), `min_points`, `window_hours` |
| `reddit`  | `subreddit`, `sort` (`top`/`new`/`hot`), `timeframe`, `limit`   |
| `search`  | `query`, `engine`, `limit`, plus engine-specific kwargs ([6 backends](./docs/getting-started/search.md)) |

### Pipeline stages

| Stage       | Effect                                                       |
|-------------|--------------------------------------------------------------|
| `dedup`     | Drop already-seen items (by canonical URL hash).             |
| `rank`      | LLM scores each item; drops below `min_relevance` (0..1).    |
| `summarize` | LLM writes a 1-line summary, attached to each item.          |
| `apply_skill` | Run a named skill (structured extraction); attaches JSON fields to `Item.structured` and auto-fills `llm_summary` from a `summary`/`one_liner`/`tldr` field. |
| `digest`    | Sets the digest header. Optionally LLM-synthesized.          |

### Sinks (fan-out)

A feed can deliver to multiple sinks in parallel. `chat_id` at the feed level is shorthand for a single Telegram sink; use `sinks:` for explicit fan-out.

```yaml
# under a feed:
sinks:
  - type: telegram
    chat_id: ${TELEGRAM_CHAT_AI}
  - type: discord
    webhook_url: ${DISCORD_WEBHOOK_URL}
  - type: ntfy
    topic: my-topic
  - type: slack
    webhook_url: ${SLACK_WEBHOOK_URL}
  - type: file
    path: /data/glean-archive.jsonl
    format: jsonl
    required: false       # failure here doesn't trigger ops alerts
  - type: webhook
    url: https://example.com/hook
    auth_bearer: ${WEBHOOK_TOKEN}
    required: false
```

| Sink | Notes |
|------|-------|
| `telegram` | Bot API; HTML/MarkdownV2/plain; auto-retry on rate limits |
| `discord` | Webhook POST; markdown; 2000-char chunking |
| `slack` | Incoming webhook; mrkdwn; 3000-char chunking |
| `ntfy` | Plain text body + `X-Title`/`X-Priority`/`X-Tags` headers |
| `webhook` | Generic HTTP POST with JSON payload (configurable headers + bearer/basic auth) |
| `file` | Append-only writes — `text`, `jsonl`, or `markdown` formats |

Full per-sink reference: [`docs/config/feeds.md`](./docs/config/feeds.md).

### Schedules

| String              | Meaning                                |
|---------------------|----------------------------------------|
| `every 30s`         | Every 30 seconds                       |
| `every 15m`         | Every 15 minutes                       |
| `every 1h`          | Every hour                             |
| `daily 09:00`       | Every day at 09:00 (`$TZ`)             |
| `@hourly`, `@daily` | Cron presets                           |
| `0 */2 * * *`       | Any 5-field cron expression            |

## Installation options

| Method | Best for | Where |
|--------|----------|-------|
| **Docker** | Self-hosters with `docker compose` | `ghcr.io/jaypetez/glean` (multi-arch, cosign-signed) |
| **Standalone binary** | Users without Python or Docker | [Releases](https://github.com/jaypetez/glean/releases): Linux (x86_64/arm64), macOS (arm64), Windows (x86_64) |
| **`.deb` / `.rpm` / `.apk`** | Distro-native installs with systemd unit | [Releases](https://github.com/jaypetez/glean/releases) (built via nfpm) |
| **From source** | Contributors | `uv venv && uv pip install -e ".[dev]"` |

## CLI

```
glean run                       # daemon; container entrypoint
glean test-feed <name>          # dry-run; prints would-be message
glean test-feed <name> --send   # like above but actually sends
glean send-now <name>           # immediate run, send for real
glean list-feeds                # feeds + last-run state
glean validate-config           # exit 0/1; prints errors
glean version
```

All commands accept `--config <path>` (default `/etc/glean/feeds.yaml`) and `--db <path>` (default `/data/state.db`).

## Operating notes

- **Bootstrap is silent.** First run of any new feed indexes current items into the seen-set without sending — only genuinely-new items go out next tick. Override with `bootstrap: send-last-N` if you want a primer.
- **State lives at `/data/state.db`.** Mount a volume. SQLite (WAL mode), inspectable with the `sqlite3` CLI.
- **Health endpoint:** `GET /healthz` on port 9090 (loopback only by default).
- **Logs:** structured key=value to stderr in dev, JSON when `LOG_FORMAT=json`.
- **Telegram rate limits:** the sender retries on `RetryAfter` automatically.
- **LLM failures during ranking:** items with failed scores are dropped (treated as `0.0`). Summarize failures fall back to the source-provided summary.
- **Optional sinks** (`required: false`) log warnings on failure but don't trigger ops alerts.

## Stability guarantee

From v1.0, the following surfaces are stable within major versions:

- **`feeds.yaml` schema** — field names, types, and defaults. New optional fields may be added; no removal without a deprecation cycle.
- **CLI commands and flags** — command names and option names are stable. No renames without a deprecated alias for one minor version.
- **Plugin protocols** — `Source.fetch`, `LLMProvider.rank/summarize/digest`, `Sink.send`, and `SearchBackend.search` method signatures are locked. New optional methods get default implementations.
- **Environment variable names** — `GLEAN_CONFIG`, `GLEAN_DB`, `TELEGRAM_BOT_TOKEN`, etc.

Breaking changes require a major version bump and are documented in release notes with a migration guide.

## Roadmap

- More first-party sinks: email (SMTP), Matrix.
- Inbound Telegram (and other) commands — `/pause <feed>`, `/run <feed>` from the chat itself.
- Embedding-based semantic dedup ("we already covered this story 2 days ago").
- Per-feed prompt versioning + A/B testing.
- LLM tool-use integration — let providers query the search layer for grounded answers.

## Plugin authoring

Glean has four plugin layers, all following the same `@register_*` decorator pattern:

| Plugin | Protocol method | Decorator | Author guide |
|--------|----------------|-----------|--------------|
| **Source** | `async fetch(ctx) -> list[Item]` | `@register_source("type")` | [`docs/plugins/source.md`](./docs/plugins/source.md) |
| **LLM Provider** | `rank` / `summarize` / `digest` / `aclose` | `@register_provider("name")` | [`docs/plugins/llm.md`](./docs/plugins/llm.md) |
| **Sink** | `async send(ctx) -> None` / `aclose` | `@register_sink("type")` | [`docs/plugins/sink.md`](./docs/plugins/sink.md) |
| **Search Backend** | `async search(query, *, http, limit) -> list[SearchResult]` | `@register_backend("name")` | [`docs/plugins/search.md`](./docs/plugins/search.md) |

For each plugin: implement the protocol, decorate with the appropriate registration call, add an import to `_import_builtins()` in the corresponding `registry.py`, and ship a unit test.

## Development

```bash
uv venv
uv pip install -e ".[dev]"
ruff check src tests
mypy src

# Standard tests (>200 unit tests, ≥80% coverage required)
uv run pytest -q

# End-to-end against mock services in Docker (mock-telegram, mock-ollama,
# mock-rss, mock-searxng) — no real API calls, fully isolated
docker compose -f docker-compose.e2e.yml up --build
curl http://localhost:8001/__messages | jq    # see what glean sent
docker compose -f docker-compose.e2e.yml down -v
```

CI runs lint + type-check + the full unit suite + the E2E stack on every PR.

## Documentation

Full docs are at [jaypetez.github.io/glean](https://jaypetez.github.io/glean) (built with MkDocs Material). Quick links:

- [Installation](./docs/getting-started/install.md)
- [Quickstart](./docs/getting-started/quickstart.md)
- [Web search setup](./docs/getting-started/search.md) — including SearXNG self-host
- [feeds.yaml reference](./docs/config/feeds.md)
- [Plugin authoring guides](./docs/plugins/)

## Contributing

Issues and PRs welcome. For non-trivial changes please open an issue first to align on direction. See [CONTRIBUTING.md](./CONTRIBUTING.md) for dev setup, testing expectations, and the Copilot code review workflow.

## License

[MIT](./LICENSE).
