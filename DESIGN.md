# glean — Design

> Topic-agnostic content aggregator that periodically pulls from multiple sources, runs items through a pluggable LLM, and posts a digest to a Telegram chat. One bot, many feeds, many chats.

**Status:** v0.1 design — locked 2026-05-12.
**License:** inherits the parent repo's MIT license.

---

## 1. Goals & non-goals

### Goals
- Run as a single self-hosted Docker container alongside Ollama (or any provider).
- One YAML file defines N independent **feeds**, each with its own sources, LLM, schedule, and target chat.
- Source-agnostic and LLM-agnostic via narrow plugin interfaces.
- Self-hoster ergonomics: friendly schedule strings, dry-run CLI, validate-config, useful error messages.
- Production-shaped from day 1 (state survives restarts, retries+backoff, alert on persistent failure).

### Non-goals (v0.1)
- Web admin UI.
- Multi-user / SaaS auth.
- Telegram bot *interaction* (replying to user commands beyond `/start` ack). Inbound commands are out of scope until v0.2.
- Embedding-based semantic dedup. v0.1 dedups by canonical URL + content-hash only.
- Search-engine indexing of past digests. Future feature.

---

## 2. High-level architecture

```
                  ┌──────────────┐
                  │  feeds.yaml  │  ← config (env-interpolated)
                  └──────┬───────┘
                         │
                         ▼
        ┌────────────────────────────────┐
        │       glean daemon       │
        │  ┌──────────────────────────┐  │
        │  │       Scheduler          │  │  APScheduler · one job per feed
        │  └────────────┬─────────────┘  │
        │               ▼                │
        │  ┌──────────────────────────┐  │
        │  │      Pipeline (per feed) │  │
        │  │  fetch → dedup → rank →  │  │
        │  │  summarize → digest →    │  │
        │  │  send                    │  │
        │  └──┬──────┬────────────┬───┘  │
        │     │      │            │      │
        │     ▼      ▼            ▼      │
        │  Sources  LLM      Telegram    │  ← plugin layers
        │  (RSS,    (Ollama,             │
        │  Scrape,  Anthropic,           │
        │  Search,  OpenAI)              │
        │  HN, RDT)                      │
        │                                │
        │           SQLite               │  ← /data/state.db (volume)
        └────────────────────────────────┘
```

### Layers
- **Config** — pydantic v2 + pydantic-settings, YAML source, `${ENV_VAR}` interpolation. Defaults+overrides merge.
- **Sources** — pluggable; each implements an async `fetch() -> list[Item]`.
- **LLM providers** — pluggable; each implements `rank`, `summarize`, `digest`.
- **Pipeline** — orchestrates the per-feed flow. Stages are declared in YAML and run in order.
- **State** — SQLite (aiosqlite). Tables: `seen_items`, `feed_runs`, `failure_counters`.
- **Telegram** — single async bot client; per-feed `chat_id`.
- **Scheduler** — APScheduler v4, AsyncIOScheduler.
- **CLI** — Typer.

---

## 3. Config schema

`feeds.yaml`:

```yaml
# Top-level defaults — every feed inherits unless overridden.
defaults:
  llm:
    provider: ollama
    model: qwen2.5:7b
    base_url: http://ollama:11434
  render:
    style: html               # html | markdown_v2 | plain
    link_preview: false
    max_items: 10
  bootstrap: skip-and-mark    # skip-and-mark | send-last-N | send-all
  failure:
    alert_after: 3            # consecutive failures before ops-chat alert
    ops_chat_id: ${TELEGRAM_OPS_CHAT_ID}

feeds:
  - name: ai-news-daily
    schedule: "every 1h"
    chat_id: ${TELEGRAM_CHAT_AI}
    sources:
      - type: rss
        url: https://simonwillison.net/atom/everything/
      - type: rss
        url: https://hnrss.org/newest?q=ai
      - type: rss
        url: http://export.arxiv.org/rss/cs.AI
    pipeline:
      - dedup
      - rank:
          prompt: |
            You are filtering an AI-news digest. Score 0-1 how relevant this is to
            a working engineer who already follows mainstream AI news.
            Drop celebrity/funding-only items. Boost releases, research, tools.
          min_relevance: 0.55
      - summarize:
          prompt: |
            One-sentence summary for a Telegram digest. Lead with the verb.
            ≤25 words. No marketing fluff.
      - digest:
          intro: "🧠 <b>AI news this hour</b>"

  - name: security-cves
    schedule: "daily 09:00"
    chat_id: ${TELEGRAM_CHAT_SEC}
    llm:
      provider: anthropic
      model: claude-haiku-4-5
    sources:
      - type: rss
        url: https://nvd.nist.gov/feeds/xml/cve/misc/nvd-rss.xml
      - type: rss
        url: https://github.com/advisories.atom
    pipeline:
      - dedup
      - rank:
          prompt: "Score 0-1: is this CVE relevant to a Python+Node+Docker stack?"
          min_relevance: 0.4
      - summarize:
          prompt: "Affected package, severity, exploit path. ≤30 words."
      - digest:
          intro: "🛡️ <b>Security advisories — daily</b>"

  - name: show-hn
    schedule: "every 3h"
    chat_id: ${TELEGRAM_CHAT_HN}
    sources:
      - type: hn
        query: "show hn"
        min_points: 25
    pipeline:
      - dedup
      - summarize:
          prompt: "What does this project do, in one line?"
      - digest:
          intro: "🚀 <b>Show HN — last 3h</b>"

  - name: localllama
    schedule: "daily 18:00"
    chat_id: ${TELEGRAM_CHAT_AI}
    sources:
      - type: reddit
        subreddit: LocalLLaMA
        sort: top
        timeframe: day
    pipeline:
      - dedup
      - summarize:
          prompt: "Summarize this Reddit post in one line."
      - digest:
          intro: "🦙 <b>r/LocalLLaMA — top of day</b>"
```

### Validation
- Pydantic validates types, required fields, schedule syntax, provider+model existence.
- `glean validate-config` returns non-zero exit on any error with **YAML line numbers** (ruamel.yaml for source positions).

---

## 4. Plugin contracts

### Source

```python
class Source(Protocol):
    type: ClassVar[str]                  # "rss", "scraper", "hn", "reddit", "search"

    async def fetch(self, ctx: FetchContext) -> list[Item]: ...
```

```python
@dataclass(frozen=True, slots=True)
class Item:
    canonical_url: str       # used for dedup
    title: str
    body: str                # may be empty; full content for LLM context
    summary: str | None      # source-provided summary if available
    source_type: str         # "rss", "hn", etc.
    source_name: str         # e.g., "hnrss.org/newest?q=ai"
    published_at: datetime | None
    score: float | None      # e.g., HN points, Reddit ups — None if N/A
    raw: dict                # full source payload for prompts that want it
```

`FetchContext` carries the http client, the feed name, the state store (so RSS can use ETag/Last-Modified), and the `since` timestamp from last successful run.

#### Concrete source plugins (v0.1)
| Type | Implementation |
|---|---|
| `rss` | `feedparser` + httpx, ETag/Last-Modified honored, redirects followed |
| `scraper` | `httpx` + `trafilatura` for full-text extraction from a list of URLs |
| `hn` | HN Algolia search API (`https://hn.algolia.com/api/v1/search_by_date`) — query, min_points, time window |
| `reddit` | `https://www.reddit.com/r/<sub>/<sort>.json` — User-Agent header required, no auth needed for read |
| `search` | Dispatch to Brave Search / Tavily / SearXNG by env var; topic → result list |

### LLMProvider

```python
class LLMProvider(Protocol):
    name: ClassVar[str]                  # "ollama", "anthropic", "openai"

    async def rank(self, item: Item, prompt: str) -> float: ...    # 0..1
    async def summarize(self, item: Item, prompt: str) -> str: ...
    async def digest(self, items: list[Item], prompt: str) -> str: ...  # optional richer digest
```

- Each provider does its own retry on transient errors with bounded backoff.
- `summarize` returns plain text (no markup). Renderer applies HTML.
- `rank` MUST return a float in `[0, 1]`. Provider clamps and parses tolerantly (e.g., "0.7", "70%", "high"→0.8).

#### Concrete LLM providers (v0.1)
| Provider | SDK | Notes |
|---|---|---|
| `ollama` | `ollama` (official Python) — `AsyncClient` | base_url configurable; defaults to `http://ollama:11434` |
| `anthropic` | `anthropic` SDK | Reads `ANTHROPIC_API_KEY` from env |
| `openai` | `openai` SDK | Reads `OPENAI_API_KEY` from env |

---

## 5. Pipeline stages

Each stage is a small async function `(items, ctx) -> items`. Stages declared in YAML; missing stages are skipped.

| Stage | Behavior |
|---|---|
| `dedup` | Drop items whose `canonical_url` (or content hash if URL missing) is in `seen_items`. |
| `rank` | Call `llm.rank(item, prompt)` per item, drop if below `min_relevance`. Parallel-bounded (sem of 4). |
| `summarize` | Call `llm.summarize(item, prompt)`, attach result as `item.llm_summary`. Parallel-bounded. |
| `digest` | Render the final message via Telegram renderer. Single LLM call optional (`provider.digest`) for an intro/header. |
| `send` | Implicit terminal stage — pushes to Telegram. Marks all items as sent in state on success. |

Stages can be reordered; e.g. `summarize` before `rank` if you want the LLM to rank its own summary (more expensive but better recall).

---

## 6. State (SQLite)

```sql
CREATE TABLE seen_items (
  feed         TEXT NOT NULL,
  item_hash    TEXT NOT NULL,             -- sha256(canonical_url) or sha256(title+body)
  url          TEXT,
  seen_at      INTEGER NOT NULL,          -- unix seconds
  sent         INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (feed, item_hash)
);

CREATE TABLE feed_runs (
  feed         TEXT PRIMARY KEY,
  last_success_at  INTEGER,
  last_attempt_at  INTEGER,
  last_error       TEXT,
  consecutive_failures INTEGER NOT NULL DEFAULT 0,
  alert_active     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE etag_cache (
  url          TEXT PRIMARY KEY,
  etag         TEXT,
  last_modified TEXT,
  cached_at    INTEGER
);
```

- Bootstrap (`skip-and-mark`): on first run, `fetch()` results are inserted into `seen_items` with `sent=1` and **no send happens**. Subsequent runs send only new items.
- Retention: pruning job once per day removes `seen_items` older than 60 days (configurable).

---

## 7. Telegram rendering

- **parse_mode:** `HTML` (Telegram's HTML is simpler/safer than MarkdownV2).
- **Link previews:** disabled (`link_preview_options.is_disabled=True`).
- **Cap:** 10 items per digest. If `fetched > 10`, the lowest-ranked overflow becomes a single line:
  *"…and 7 more (lowest relevance items hidden)."*
- **4096-char limit:** if the rendered digest exceeds 4096 chars, split into N messages, each prefixed `(part k/N)`.
- **Item template:**
  ```html
  <b>{title}</b>
  {llm_summary}
  <i>{source_emoji} {source_name}</i> · <a href="{url}">link</a>
  ```
- Source emoji map: `rss→📰, hn→🟠, reddit→👽, scraper→🔍, search→🌐`.

---

## 8. Scheduler

- APScheduler v4, AsyncIOScheduler, in-memory job store (state is in our own SQLite).
- Friendly interval parser accepts:
  - `every <N>(s|m|h|d)` → IntervalTrigger
  - `daily HH:MM` → CronTrigger
  - `hourly`, `@hourly` → CronTrigger `0 * * * *`
  - Raw 5-field cron → CronTrigger (escape hatch)
- Misfire policy: `grace_time=300s`, `coalesce=True`. If the bot was down, runs at most once on recovery, not the missed N times.
- All times in `TZ` env var (defaults to UTC).

---

## 9. Failure model

Per-feed counter in `feed_runs.consecutive_failures`.

| Outcome | Effect |
|---|---|
| Success | `consecutive_failures=0`. If `alert_active=1`, post `✅ <feed> recovered` to ops chat and clear flag. |
| Failure | Increment counter. Log structured error. **Don't** retry within the same tick (next scheduled tick is the retry — keeps semantics simple). |
| `consecutive_failures >= alert_after` (default 3) AND `alert_active=0` | Post `🚨 <feed> failing — <error>` to ops chat. Set `alert_active=1`. No re-alerts until recovery. |

Transient HTTP / LLM 429s/5xxs use **in-tick exponential backoff** (3 attempts, 1s→2s→4s) before counting as a feed failure.

---

## 10. CLI

```
glean run                          # main daemon — container entrypoint
glean test-feed <name>             # dry-run; print would-be message; no state writes, no Telegram
glean test-feed <name> --send      # like above but actually sends (still writes state)
glean list-feeds                   # show feeds + next-run-at + last-result
glean validate-config              # exit 0 if feeds.yaml is valid, exit 1 with error+line otherwise
glean send-now <name>              # trigger one feed immediately, off-schedule
glean version
```

All commands share `--config <path>` (default `/etc/glean/feeds.yaml`) and `--log-level`.

---

## 11. Secrets & config layout

- All secrets via env (loaded by docker-compose from `.env`):
  - `TELEGRAM_BOT_TOKEN` (required)
  - `TELEGRAM_CHAT_*` — chat IDs referenced by `feeds.yaml` via `${VAR}`
  - `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `BRAVE_API_KEY`, `TAVILY_API_KEY` — optional, only if those providers/sources are used
- `feeds.yaml` is plain (no secrets); safe to commit.
- `.env.example` shipped; `.env` is gitignored.

---

## 12. Distribution

- **Dockerfile** — multi-stage: `python:3.12-slim` builder with `uv pip install`, then a runtime stage with only the venv + app code. Non-root user `glean`. `HEALTHCHECK` hits internal `/healthz` (in-process HTTP server on port 9090).
- **docker-compose.yml** — services:
  - `glean` (this app), volume `./data:/data`
  - `ollama` (default LLM backend), volume `ollama-models:/root/.ollama`, port 11434 internal only by default
- **CI** — GitHub Actions:
  - Lint (`ruff`), type-check (`mypy`), tests (`pytest`).
  - On push to `main`: build + push `ghcr.io/jaypetez/glean:{sha,latest}`.
- **Versioning** — semver; `glean version` prints embedded git SHA + version tag.

---

## 13. Observability

- Structured logging via `structlog` to stdout (JSON in production, key=value in dev).
- Per-run log line: `feed=ai-news fetched=42 deduped=18 ranked=11 sent=10 duration_ms=8341`.
- `/healthz` returns 200 if scheduler is running and DB is reachable; 503 otherwise.
- `/metrics` (optional, v0.2) — Prometheus counters: `runs_total{feed,outcome}`, `items_sent_total{feed}`, `llm_calls_total{provider}`, `llm_latency_seconds`.

---

## 14. Project layout

```
glean/
├── DESIGN.md                       # this doc
├── README.md
├── pyproject.toml                  # uv + ruff + mypy + pytest
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── feeds.example.yaml
├── src/glean/
│   ├── __init__.py
│   ├── __main__.py                 # → cli.app()
│   ├── config/
│   │   ├── schema.py               # pydantic models
│   │   ├── loader.py               # yaml + env interpolation
│   │   └── schedule.py             # friendly interval parser
│   ├── sources/
│   │   ├── base.py                 # Source protocol, Item dataclass
│   │   ├── rss.py
│   │   ├── scraper.py
│   │   ├── hn.py
│   │   ├── reddit.py
│   │   └── search.py
│   ├── llm/
│   │   ├── base.py                 # LLMProvider protocol
│   │   ├── ollama.py
│   │   ├── anthropic.py
│   │   └── openai.py
│   ├── pipeline/
│   │   ├── engine.py
│   │   └── stages.py               # dedup, rank, summarize, digest
│   ├── telegram/
│   │   ├── client.py
│   │   └── render.py
│   ├── state/
│   │   ├── store.py                # aiosqlite wrapper
│   │   └── migrations.py
│   ├── cli/
│   │   └── app.py                  # Typer commands
│   ├── scheduler.py
│   ├── health.py                   # /healthz mini HTTP server
│   └── logging.py
├── tests/
│   ├── unit/
│   └── integration/
└── docs/
    ├── plugins.md                  # author a new Source/Provider
    └── troubleshooting.md
```

---

## 15. Open questions deferred to v0.2

- Inbound Telegram commands (`/list`, `/pause feed`, `/run feed`).
- Embedding-based semantic dedup ("we already covered this story 2 days ago").
- Web admin UI.
- Per-feed prompt versioning + A/B testing.
- Postgres backend for multi-instance deployments.
