# glean

Self-hosted, pluggable personal agent that gleans signal from RSS, scraping, search, and APIs — processes it with any LLM, then delivers on a schedule to whatever sink you wire up.

## What is glean?

glean is a small Python daemon that runs as a Docker container. You describe **feeds** in a YAML file — each one is a recipe of `sources → LLM pipeline → sink → schedule`. It deduplicates, ranks, summarizes, and posts a clean digest. One container, many topics, many sinks.

## Features

- **Pluggable sources** — RSS/Atom, web scraping, Hacker News, Reddit, web search (Brave / Tavily / SearXNG)
- **Pluggable LLM** — Ollama (default), Anthropic, OpenAI. Per-feed provider/model
- **Per-feed pipeline** — declare stages in YAML: `dedup → rank → summarize → digest`
- **Smart dedup** — SQLite-backed, persists across restarts
- **Friendly schedules** — `every 1h`, `every 15m`, `daily 09:00`, or raw cron
- **Failure-aware** — exponential backoff, ops-chat alerts after N consecutive failures
- **One container** — `docker compose up`

## Quick links

- [Installation](getting-started/install.md)
- [Quickstart](getting-started/quickstart.md)
- [Configuration Reference](config/feeds.md)
- [Writing Plugins](plugins/source.md)
