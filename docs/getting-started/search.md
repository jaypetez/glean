# Web search setup

glean supports several web search backends as data sources. This page walks
through the most common configurations.

## Backend overview

| Backend | Self-hosted | API key | Cost | Best for |
|---------|-------------|---------|------|----------|
| `searxng` |  Yes | None | $0 | Local LLM users, privacy-conscious self-hosters |
| `brave` | No | Required | ~$3/1k queries (2k/mo free) | Best independent index |
| `tavily` | No | Required | ~$3/1k queries (1k/mo free) | LLM-friendly answer synthesis |
| `serper` | No | Required | $1/1k queries (2.5k free credits) | Google-quality results |
| `exa` | No | Required | $7/1k queries (1k/mo free) | Semantic search + full content |
| `mwmbl` | No | None | $0 | Free, open-source crawler (limited index) |

**Recommendation for most users:** start with **SearXNG**  it's free, runs in
one container, and aggregates 230+ search engines. Only reach for cloud APIs if
you need their specific features.

## SearXNG setup (recommended)

### 1. Generate a secret

```bash
echo "SEARXNG_SECRET=$(openssl rand -hex 32)" >> .env
```

### 2. Uncomment the searxng service

In `docker-compose.yml`, find the `# searxng:` block (near the bottom) and
uncomment it.

### 3. Verify the config template exists

The repo ships `searxng-config/settings.yml` with sensible defaults for a
private single-user instance. No edits needed unless you want to customize
the engine list.

### 4. Start the stack

```bash
docker compose up -d
```

SearXNG is now running at `http://searxng:8080`  accessible from the glean
container but not exposed to the host.

### 5. Use it in feeds.yaml

```yaml
sources:
  - type: search
    query: "AI safety research"
    engine: searxng
    base_url: http://searxng:8080
    categories: general,news    # comma-separated SearXNG categories
    time_range: day             # day | week | month | year
    limit: 10
```

### 6. Test it

```bash
docker exec -it glean glean test-feed your-feed-name
```

If you see `RuntimeError: SearXNG returned 403 Forbidden`, your settings.yml
doesn't have `json` in `search.formats`. The shipped template already has it,
so this only happens if you've customized the file.

## Cloud backend setup

### Brave

```bash
echo "BRAVE_API_KEY=your-key" >> .env
```

```yaml
sources:
  - type: search
    query: "..."
    engine: brave
```

Get a key at https://brave.com/search/api/.

### Tavily

```bash
echo "TAVILY_API_KEY=tvly-..." >> .env
```

```yaml
sources:
  - type: search
    query: "..."
    engine: tavily
    search_depth: basic  # or "advanced"  fetches and parses full pages
```

Get a key at https://tavily.com.

### Serper.dev (Google SERP)

```bash
echo "SERPER_API_KEY=..." >> .env
```

```yaml
sources:
  - type: search
    query: "..."
    engine: serper
    country: us
```

Get a key at https://serper.dev.

### Exa (semantic search)

```bash
echo "EXA_API_KEY=..." >> .env
```

```yaml
sources:
  - type: search
    query: "vector database benchmarks 2025"
    engine: exa
    type: auto              # neural | keyword | auto
    include_text: false      # set true to include full page text (large!)
```

Get a key at https://exa.ai.

## Multi-backend feeds

You can mix backends in a single feed:

```yaml
feeds:
  - name: ai-research
    schedule: "every 1h"
    chat_id: ${TELEGRAM_CHAT_AI}
    sources:
      - type: search
        query: "LLM evaluation"
        engine: searxng
        base_url: http://searxng:8080
      - type: search
        query: "transformer optimization"
        engine: brave
      - type: search
        query: "embedding models"
        engine: exa
        include_text: false
    pipeline:
      - dedup
      - rank: { prompt: "Score 0-1: relevance to ML researchers", min_relevance: 0.4 }
      - summarize: { prompt: "One-sentence summary." }
      - digest: { intro: " AI research" }
```

## Adding a new backend

See [docs/plugins/source.md](../plugins/source.md) for the source authoring guide.
