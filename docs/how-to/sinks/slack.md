---
title: "How to set up Slack — glean"
description: "Send glean digests to Slack with an incoming webhook."
---

# How to set up Slack

**Goal:** Post each feed digest into a Slack channel through an incoming webhook.

**You need:**

- Permission to create or configure a Slack app.
- A Slack channel for digests.
- A secure place to store the webhook URL, such as `.env`.

## Steps

1. Go to [api.slack.com/apps](https://api.slack.com/apps), create or open your app, and select **Incoming Webhooks**.
2. Turn incoming webhooks on, choose **Add New Webhook to Workspace**, pick the channel, and copy the webhook URL.
3. Store the URL in `.env`:

   ```dotenv
   SLACK_WEBHOOK_AI=<slack-webhook-url>
   ```

   Slack webhook URLs use this shape: `https://hooks.slack.com/services/TXXXXXXXX/BXXXXXXXX/<token>`.

4. Add a Slack sink to the feed:

   ```yaml
   feeds:
     - name: ai-news
       schedule: "every 1h"
       sinks:
         - type: slack
           webhook_url: ${SLACK_WEBHOOK_AI}
       sources:
         - type: rss
           url: https://example.com/feed.xml
       pipeline:
         - dedup
         - summarize
         - digest
   ```

5. Optional: set Slack display overrides if your Slack app allows them:

   ```yaml
   sinks:
     - type: slack
       webhook_url: ${SLACK_WEBHOOK_AI}
       channel: "#ai-news"
       username: glean
       icon_emoji: ":newspaper:"
   ```

6. Use Slack mrkdwn normally. glean renders titles as `*bold*`, links as `<url|title>`, and escapes mrkdwn characters in item text.

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

If the webhook URL is malformed, validation fails before the daemon starts.

## Next steps

- [Set up Discord for another webhook-based chat sink](discord.md)
- [Slack sink reference](../../config/feeds.md#slack)
