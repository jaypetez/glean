---
title: "How to set up OpenAI — glean"
description: "Use OpenAI models for glean ranking, summaries, and digest headers."
---

# How to set up OpenAI

**Goal:** Run a feed with OpenAI as the LLM provider.

**You need:**

- An OpenAI account with billing enabled.
- An OpenAI API key.
- A secure place to store the key, such as `.env`.

## Steps

1. Create an API key in the OpenAI dashboard.
2. Store the key in `.env`:

   ```dotenv
   OPENAI_API_KEY=<openai-api-key>
   ```

3. Choose a model:

   - `gpt-4o-mini` for lower cost.
   - `gpt-4o` for higher quality.

4. Configure the default LLM:

   ```yaml
   defaults:
     llm:
       provider: openai
       model: gpt-4o-mini
   ```

5. Or configure one feed only:

   ```yaml
   feeds:
     - name: ai-news
       schedule: "every 1h"
       llm:
         provider: openai
         model: gpt-4o-mini
       max_llm_calls_per_run: 50
       sinks:
         - type: file
           path: /data/ai-news.txt
       sources:
         - type: rss
           url: https://example.com/feed.xml
       pipeline:
         - dedup
         - rank: { prompt: "Score relevance to AI builders", min_relevance: 0.5 }
         - summarize
         - digest
   ```

6. Set `max_llm_calls_per_run` on paid feeds. `rank`, `summarize`, `apply_skill`, and LLM-generated `digest` calls all count toward the cap.

## Verify

Run:

```bash
uv run glean validate-config -c feeds.yaml
```

Expected output includes:

```text
OK — 1 feed(s)
  - ai-news: schedule='every 1h' sources=1
```

## Next steps

- [Set up per-source LLM dispatch to limit paid calls](per-source.md)
- [LLM provider reference](../../config/feeds.md#llm-providers)
