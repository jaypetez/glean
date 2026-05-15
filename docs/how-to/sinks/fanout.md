---
title: "How to set up sink fanout — glean"
description: "Send one glean feed to multiple sinks in parallel."
---

# How to set up sink fanout

**Goal:** Deliver one feed digest to several destinations from the same feed run.

**You need:**

- Two or more configured sink destinations.
- Any required tokens or webhook URLs in `.env`.
- A decision about which sinks must succeed.

## Steps

1. Put sink secrets in `.env`:

   ```dotenv
   TELEGRAM_BOT_TOKEN=<bot-token-from-botfather>
   TELEGRAM_CHAT_AI=<telegram-chat-id>
   DISCORD_WEBHOOK_AI=<discord-webhook-url>
   ```

2. Add multiple entries under `sinks:`:

   ```yaml
   feeds:
     - name: ai-news
       schedule: "every 1h"
       sinks:
         - type: telegram
           chat_id: ${TELEGRAM_CHAT_AI}
         - type: discord
           webhook_url: ${DISCORD_WEBHOOK_AI}
           required: false
         - type: file
           path: /data/archives/ai-news.md
           format: markdown
       sources:
         - type: rss
           url: https://example.com/feed.xml
       pipeline:
         - dedup
         - summarize
         - digest
   ```

3. Leave `required` unset for destinations that must succeed; the default is `true`.
4. Set `required: false` for optional mirrors. Optional sink failures are logged but do not fail the feed run, increment failure counters, or trigger ops alerts.
5. Do not rely on sink order. glean sends to all configured sinks in parallel.

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

- [Set up Telegram as a required primary sink](telegram.md)
- [Sinks reference](../../config/feeds.md#sinks)
