---
title: "How to set up per-source LLM dispatch — glean"
description: "Use different LLM providers for different sources in one glean feed."
---

# How to set up per-source LLM dispatch

**Goal:** Use Ollama for cheap RSS items and Claude for a curated newsletter in the same feed.

**You need:**

- A working default LLM, such as bundled Ollama.
- Any paid-provider API keys needed by source overrides.
- A feed with two or more sources.

## Steps

1. Put paid-provider keys in `.env`:

   ```dotenv
   ANTHROPIC_API_KEY=<anthropic-api-key>
   ```

2. Set the cheap default LLM for the feed or all feeds:

   ```yaml
   defaults:
     llm:
       provider: ollama
       model: qwen2.5:7b
   ```

3. Add your noisy or high-volume source without an `llm` block so it uses the default:

   ```yaml
   sources:
     - type: rss
       url: https://example.com/noisy.xml
   ```

4. Add `llm` to the curated source that should use Claude:

   ```yaml
   sources:
     - type: rss
       url: https://example.com/noisy.xml
     - type: rss
       url: https://example.com/curated-newsletter.xml
       llm:
         provider: anthropic
         model: claude-haiku-4-5
   ```

5. Put the sources into the full feed:

   ```yaml
   defaults:
     llm:
       provider: ollama
       model: qwen2.5:7b

   feeds:
     - name: mixed-ai-news
       schedule: "every 1h"
       max_llm_calls_per_run: 60
       sinks:
         - type: file
           path: /data/mixed-ai-news.md
           format: markdown
       sources:
         - type: rss
           url: https://example.com/noisy.xml
         - type: rss
           url: https://example.com/curated-newsletter.xml
           llm:
             provider: anthropic
             model: claude-haiku-4-5
       pipeline:
         - dedup
         - rank: { prompt: "Score usefulness for AI builders", min_relevance: 0.5 }
         - summarize
         - digest
   ```

6. Use the same pipeline as usual. `rank`, `summarize`, and `apply_skill` dispatch each item to the LLM attached to its source.

## Verify

Run:

```bash
uv run glean validate-config -c feeds.yaml
```

Expected output includes:

```text
OK — 1 feed(s)
  - mixed-ai-news: schedule='every 1h' sources=2
```

## Next steps

- [Set up Ollama as the cheap default provider](ollama.md)
- [Per-source LLM reference](../../config/feeds.md#per-source-llm)
