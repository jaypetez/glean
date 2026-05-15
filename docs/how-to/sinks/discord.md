---
title: "How to set up Discord — glean"
description: "Send glean digests to a Discord channel with an incoming webhook."
---

# How to set up Discord

**Goal:** Post each feed digest into a Discord channel through a webhook.

**You need:**

- Manage Webhooks permission on the Discord server.
- A target text channel.
- A secure place to store the webhook URL, such as `.env`.

## Steps

1. In Discord, open **Server Settings → Integrations → Webhooks → Create Webhook**.
2. Pick the target channel, name the webhook, and copy the webhook URL.
3. Store the URL in `.env`:

   ```dotenv
   DISCORD_WEBHOOK_AI=<discord-webhook-url>
   ```

   Discord webhook URLs use this shape: `https://discord.com/api/webhooks/<digits>/<token>`.

4. Add a Discord sink to the feed:

   ```yaml
   feeds:
     - name: ai-news
       schedule: "every 1h"
       sinks:
         - type: discord
           webhook_url: ${DISCORD_WEBHOOK_AI}
       sources:
         - type: rss
           url: https://example.com/feed.xml
       pipeline:
         - dedup
         - summarize
         - digest
   ```

5. Optional: override the webhook display name and avatar:

   ```yaml
   sinks:
     - type: discord
       webhook_url: ${DISCORD_WEBHOOK_AI}
       username: glean
       avatar_url: https://example.com/glean-avatar.png
   ```

6. Leave Markdown in your item titles and summaries as-is. glean escapes Discord markdown characters before sending and disables parsed mentions with `allowed_mentions`.

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

- [Set up Slack for another chat destination](slack.md)
- [Discord sink reference](../../config/feeds.md#discord)
