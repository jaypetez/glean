---
title: "How to set up Anthropic — glean"
description: "Use Anthropic Claude models for glean ranking, summaries, digests, and structured extraction."
---

# How to set up Anthropic

**Goal:** Run a feed with Anthropic Claude as the LLM provider.

**You need:**

- An Anthropic account with API access.
- An Anthropic API key.
- A secure place to store the key, such as `.env`.

## Steps

1. Create an API key in the Anthropic console.
2. Store the key in `.env`:

   ```dotenv
   ANTHROPIC_API_KEY=<anthropic-api-key>
   ```

3. Choose a model:

   - `claude-haiku-4-5` for lower cost.
   - `claude-sonnet-4-5` for higher quality.

4. Configure the default LLM:

   ```yaml
   defaults:
     llm:
       provider: anthropic
       model: claude-haiku-4-5
   ```

5. Or configure one feed only:

   ```yaml
   feeds:
     - name: security-news
       schedule: "every 1h"
       llm:
         provider: anthropic
         model: claude-sonnet-4-5
       max_llm_calls_per_run: 40
       sinks:
         - type: file
           path: /data/security-news.md
           format: markdown
       sources:
         - type: rss
           url: https://example.com/security.xml
       pipeline:
         - dedup
         - rank: { prompt: "Score severity for security engineers", min_relevance: 0.6 }
         - summarize
         - digest
   ```

6. Use `apply_skill` normally when you need structured extraction. The Anthropic provider uses forced tool-use for structured output.
7. Set `max_llm_calls_per_run` on paid feeds so high-volume sources cannot exceed your intended call budget.

## Verify

Run:

```bash
uv run glean validate-config -c feeds.yaml
```

Expected output includes:

```text
OK — 1 feed(s)
  - security-news: schedule='every 1h' sources=1
```

## Next steps

- [Set up OpenAI if you want another hosted provider option](openai.md)
- [LLM provider reference](../../config/feeds.md#llm-providers)
