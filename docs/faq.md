---
title: "FAQ — glean FAQ"
description: Answers to common questions about running, configuring, securing, and troubleshooting glean.
---

# FAQ

## Getting Started

### What is glean?

glean is a self-hosted personal agent for recurring information digests. You define feeds in `feeds.yaml`; each feed pulls from sources such as RSS, web pages, Reddit, Hacker News, or search, runs the items through an LLM pipeline, deduplicates them, and sends the result to one or more sinks.

The core idea is narrow on purpose: "periodically pull signal from places I care about, summarize it, and deliver it where I already read messages." It is not a full workflow platform or hosted SaaS; it is a small daemon you can run in one Docker container with local state.

### Does it work without Telegram?

Yes. Telegram was the first sink and many examples still use it, but current glean feeds can fan out to Telegram, Discord, Slack, ntfy, generic webhooks, and append-only files. The legacy `chat_id` shorthand still creates a Telegram sink, while the newer `sinks:` list lets you configure one or many destinations explicitly.

If you do not want any chat app involved, use the `file` sink for text, Markdown, or JSONL archives, or use the webhook sink to hand digests to another system. You can also mark secondary sinks as `required: false` so a flaky mirror destination does not make the whole feed fail.

### Can I use it without a VPS?

Yes. glean only needs an always-on place to run: a laptop, home server, NAS, Raspberry Pi, or small cloud VM all work. Docker Compose is the simplest path because it brings the app and optional Ollama service up together.

If you do not have a machine that stays online, you can still run `glean send-now <feed>` from a scheduler such as cron, Task Scheduler, or CI, but the built-in APScheduler daemon is designed for a persistent process. For most users, a home server or low-cost VM is enough.

### Does it cost money to run?

The software is open source, and a local Ollama model can keep LLM inference free after you provide the hardware. RSS, Reddit, Hacker News, SearXNG, MWMBL, and file sinks can also run without paid API keys.

Costs appear when you choose paid infrastructure or providers: a VPS, hosted LLM APIs, paid search APIs such as Brave/Tavily/Serper/Exa, or paid chat/workspace plans. Use `max_llm_calls_per_run`, per-feed models, and per-source LLM overrides to keep paid calls predictable.

## Configuration

### What LLM should I use?

Start with Ollama and `qwen2.5:7b` if you want local, private, low-cost summaries and have enough RAM to run it. It is the default path in the Docker Compose examples and works well for short digests, ranking, and lightweight extraction.

Use Anthropic or OpenAI when quality matters more than locality, when a feed is especially noisy, or when structured extraction needs stronger instruction following. You can mix models: set a cheap default, override one feed with a hosted provider, or override only one noisy source inside a feed.

### How do I add a Reddit feed?

Use the built-in `reddit` source. It reads public subreddit JSON without OAuth and supports `subreddit`, `sort`, `timeframe`, and `limit` fields, so a basic feed is only a few lines of YAML.

```yaml
feeds:
  - name: localllama
    schedule: "daily 18:00"
    sources:
      - type: reddit
        subreddit: LocalLLaMA
        sort: top
        timeframe: day
        limit: 25
    pipeline:
      - dedup
      - summarize: { prompt: "Summarize this Reddit post in one line." }
      - digest: { intro: "🦙 r/LocalLLaMA — top of day" }
    sinks:
      - type: telegram
        chat_id: ${TELEGRAM_CHAT_AI}
```

Reddit can throttle aggressive clients, so keep schedules and limits reasonable. If you only want highly relevant posts, add a `rank` stage before `summarize` and set `min_relevance` to drop low-signal items.

### Can I run multiple feeds with different LLMs?

Yes. Each feed can set its own `llm:` block, and each source can also override the feed/default LLM. The precedence is `Skill LLM > Source LLM > Feed LLM > Defaults LLM`, which lets you spend premium calls only where they help.

```yaml
defaults:
  llm: { provider: ollama, model: qwen2.5:7b, base_url: http://ollama:11434 }

feeds:
  - name: ai-news
    llm: { provider: ollama, model: qwen2.5:7b }
    sources: [{ type: rss, url: https://simonwillison.net/atom/everything/ }]

  - name: security-cves
    llm: { provider: anthropic, model: claude-haiku-4-5 }
    sources: [{ type: rss, url: https://github.com/advisories.atom }]
```

This is useful when one feed is high-volume and cheap, while another feed is lower-volume but needs better reasoning. Add `max_llm_calls_per_run` if you use paid providers and want a hard budget per tick.

## Operations

### Is my data private?

glean stores configuration and state locally: `feeds.yaml`, `.env`, the SQLite database under `/data`, and any file sink outputs you configure. It does not require a hosted glean account, and the app is designed so secrets live in `.env` instead of committed YAML.

Privacy depends on the providers and sinks you choose. Local Ollama keeps prompts on your machine; hosted LLMs, hosted search APIs, Telegram, Discord, Slack, ntfy, and webhooks receive the content you send them. For sensitive feeds, prefer local providers, protect `/data` with `chmod 700`, keep `GLEAN_DISABLE_AUTH` off in production, and expose the Web UI only on loopback or behind trusted auth.

### How do I back up?

Back up four things: `feeds.yaml`, `.env`, the `/data` directory, and any files written by file sinks. The SQLite state database tracks seen items, bootstrap status, ETags, and run history, so keeping it preserves dedup behavior across restores.

For a simple cold backup, stop the container and copy the bind mount. For a live backup, use SQLite's backup mode from inside the container or copy the whole volume only after making sure writes are quiescent. Store `.env` separately and securely because it contains API keys and chat IDs.

## Troubleshooting

### Why isn't anything sending? (bootstrap explanation)

By default, a new feed uses `bootstrap: skip-and-mark`. On the first run, glean indexes the current items as already seen and sends nothing, which prevents a surprise dump of every old article in a feed. Only items that appear after bootstrap are sent on later ticks.

Check `glean list-feeds` or run `glean test-feed <name>` to see whether the feed is pre-bootstrap or simply has no new items. If you want the first run to send a starter batch, set `bootstrap: send-last-N` and `bootstrap_count: 5`; if you want to reset a feed, delete its `seen_items` and `feed_runs` rows as shown in Troubleshooting.

### How is this different from n8n / RSSHub / FreshRSS?

glean overlaps with those tools, but it is not trying to replace all of them. n8n and Huginn are broad automation platforms, RSSHub is a feed adapter, and FreshRSS/Miniflux are reader UIs; glean is a specialized content-digest agent with LLM ranking/summarization and scheduled delivery to chat or sink destinations.

The best choice depends on where you want to spend complexity. If you need arbitrary workflows or a reading inbox, choose the other tool; if you want one container that turns feeds/search/scrapes into LLM-written digests, choose glean. See the [comparison guide](./about/comparison.md) for honest tradeoffs.
