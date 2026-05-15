---
title: "Roadmap — glean About"
description: Current status and possible future directions for glean, grouped by planning horizon.
---

# Roadmap

This roadmap is directional, not a promise of dates. glean is a single-maintainer project, so priorities may shift based on security fixes, maintainer availability, and community contributions.

No open GitHub issues currently carry the `roadmap` label. The items below come from the README status/roadmap, the architecture notes, recent release history, and recurring gaps in the docs.

## Now (in v1.3.0)

- Stable feed pipeline: sources → dedup → rank → summarize → `apply_skill` → digest → sinks.
- Four plugin layers: Source, Sink, LLM Provider, and Search Backend.
- Built-in sources for RSS, scraper URLs, Hacker News, Reddit, and web search.
- Built-in sinks for Telegram, Discord, Slack, ntfy, webhook, and file output.
- LLM providers for Ollama, Anthropic, and OpenAI, with feed/source/skill-level model overrides.
- Web UI and REST API for configuring feeds, editing skills, rotating the API key, and watching live status over SSE.
- Security hardening from the v1.2 audit: SSRF protection, prompt-injection guards, output filtering, secret scrubbing, file path allowlists, HTTP hardening, container hardening, and SQLite PRAGMAs.
- v1.3 reliability and agent-friendliness work: yoyo state migrations, DST regression tests, property/API fuzz tests, E2E hardening, trace IDs, richer `/healthz`, Makefile/pre-commit workflow, and AGENTS/Copilot guidance.

## Next (planned for v1.4 / v2.0)

- More first-party sinks, especially email (SMTP) and Matrix.
- Inbound chat commands such as `/pause <feed>` and `/run <feed>` from Telegram or other chat surfaces.
- Embedding-based semantic dedup so near-duplicate stories can be suppressed even when URLs differ.
- Per-feed prompt versioning and A/B testing for ranking, summarization, and structured skills.
- LLM tool-use integration so providers can query the search layer for grounded follow-up context.
- Optional Prometheus-style metrics for feed runs, sent items, LLM calls, and latency.
- Multi-user/RBAC work for v2.x; today glean remains a single-user service protected by one API key.

## Maybe (community ideas being considered)

- More source adapters and search backends, especially for communities that do not expose clean RSS.
- Browser or bookmarklet workflows for turning ad hoc pages into scraper feeds.
- Searchable archives of past digests, likely built on top of file sinks or a separate index.
- Better hosted-model cost dashboards and budget warnings beyond `max_llm_calls_per_run`.
- Recipe packs for common use cases such as job monitoring, release tracking, vulnerability triage, and local community alerts.
- Additional deployment packaging if maintainers appear for a specific ecosystem.

If you want to help, open a focused issue first so the scope can be aligned before implementation.
