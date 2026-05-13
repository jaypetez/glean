# Per-source LLM models

Each source within a feed can specify its own LLM. This lets you mix cheap
local models for noisy sources with premium APIs for curated ones.

## Why

A typical multi-source feed might pull from:

- a noisy RSS aggregator (200 items per tick, mostly noise)
- a curated subreddit (5 items per tick, mostly signal)
- a security advisory feed (high-stakes summaries)

You probably want:
- Local Ollama for the noisy RSS (cheap, fast, good enough)
- Claude Haiku for the subreddit (smart enough, still cheap)
- Claude Sonnet for the security feed (worth the cost, low volume)

## How

Add `llm:` to any source spec:

```yaml
defaults:
  llm: { provider: ollama, model: qwen2.5:7b }   # fallback

feeds:
  - name: tech
    schedule: "every 1h"
    chat_id: ${TELEGRAM_CHAT_TECH}
    sources:
      - type: rss                           # uses defaults.llm (Ollama)
        url: https://example.com/noisy.xml

      - type: reddit                        # cheap Haiku for curated content
        subreddit: programming
        sort: top
        timeframe: hour
        llm:
          provider: anthropic
          model: claude-haiku-4-5

      - type: rss                           # premium Sonnet for high-stakes
        url: https://nvd.nist.gov/feeds/xml/cve/misc/nvd-rss.xml
        llm:
          provider: anthropic
          model: claude-sonnet-4-5
    pipeline:
      - dedup
      - rank: { prompt: "...", min_relevance: 0.6 }
      - summarize: { prompt: "..." }
      - digest
```

The `llm:` block accepts the same fields as `defaults.llm` and `feeds[].llm`:
`provider`, `model`, `base_url`, `api_key`, `timeout_s`.

## How it works

When the source fetches items, the runner tags each item with an opaque LLM
key (`{provider}:{model}:{base_url}`). When `rank`/`summarize`/`apply_skill`
runs, each item is dispatched to its own LLM. Sources that share the same LLM
config share a single cached provider instance, so this is memory-efficient.

## Precedence

For `summarize` and `rank` stages: **source LLM > feed LLM > defaults.llm**.

For `apply_skill`: **skill LLM > source LLM > feed LLM > defaults.llm** (skills
can demand a specific model — see [Skills](skills.md)).

Sources without `llm:` use the feed default (or `defaults.llm`).

## Cost optimization patterns

```yaml
# Pattern 1: free local for everything except critical sources
sources:
  - type: rss
    url: https://aggregator.com/everything.xml   # free Ollama via defaults
  - type: rss
    url: https://important.com/critical.xml
    llm: { provider: openai, model: gpt-4o }     # premium for critical
```

```yaml
# Pattern 2: per-domain quality tier
sources:
  - type: search
    query: "noise topic"
    engine: searxng
    llm: { provider: ollama, model: qwen2.5:3b }  # tiny model for noise
  - type: search
    query: "important topic"
    engine: brave
    llm: { provider: anthropic, model: claude-sonnet-4-5 }  # sonnet for signal
```
